"""Calibrated DigitalMicrograph DM3/DM4 image loader.

Read the *scientific* pixels, not an annotated presentation screenshot. DM3/DM4
format handling is delegated to RosettaSciIO. No invented calibration: if either
spatial axis is uncalibrated then all physical-size outputs remain null.
"""
from __future__ import annotations
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import numpy as np

UNIT_TO_NM = {
    'nm':1., 'nanometer':1., 'nanometre':1., 'nanometers':1.,
    'um':1000., 'µm':1000., 'μm':1000., 'micrometer':1000., 'micrometre':1000.,
    'pm':0.001, 'a':0.1, 'å':0.1, 'angstrom':0.1, 'ångström':0.1,
    'm':1e9, 'mm':1e6,
}


def nm_scale(axis: dict[str, Any]) -> float | None:
    """Return nm per pixel; never assume unrecognized units mean nanometers."""
    u = str(axis.get('units') or '').strip().lower().replace('\\u00b5','µ')
    if u not in UNIT_TO_NM:
        return None
    scale = axis.get('scale')
    try:
        v = abs(float(scale)) * UNIT_TO_NM[u]
    except (ValueError, TypeError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def dm_header_version(path: str | Path) -> int:
    with open(path, 'rb') as f:
        head = f.read(4)
    if len(head) != 4: raise ValueError('Truncated DM3/DM4 header')
    version = struct.unpack('>I', head)[0]
    if version not in (3,4):
        raise ValueError(f'Not a DM3/DM4 file: header version {version}')
    return version


def inspect_datasets(datasets: list[dict]) -> list[dict]:
    result=[]
    for i,d in enumerate(datasets):
        a=np.asarray(d['data'])
        axes=d.get('axes') or []
        result.append(dict(index=i,shape=list(a.shape),dtype=str(a.dtype),
                           ndim=a.ndim,axes=[{k:ax.get(k) for k in ('name','units','scale','size','index_in_array')} for ax in axes]))
    return result


def select_dataset(datasets: list[dict], index: int | None = None, frame: int | None = None) -> tuple[np.ndarray,dict]:
    """Select a 2D image. For 3D, require both dataset choice and frame choice."""
    if not datasets: raise ValueError('No datasets in DM file')
    if index is None:
        choices=[i for i,d in enumerate(datasets) if np.asarray(d['data']).ndim == 2]
        if len(choices)!=1:
            raise ValueError(f'Expected exactly one 2D dataset, found {len(choices)}; pass --dataset-index')
        index=choices[0]
    if not 0 <= index < len(datasets): raise IndexError('Invalid dataset index')
    dataset=datasets[index]
    full=np.asarray(dataset['data'])
    if full.ndim==3:
        if frame is None: raise ValueError('3D dataset requires explicit --frame')
        if not 0 <= frame < full.shape[0]: raise IndexError('Invalid frame index')
        arr=full[frame]
    elif full.ndim==2:
        if frame is not None: raise ValueError('--frame only supports 3D datasets')
        arr=full
    else:
        raise ValueError(f'Unsupported {full.ndim}D dataset; select 2D TEM, not spectrum/4D scan')
    if not np.issubdtype(arr.dtype,np.number) or np.iscomplexobj(arr):
        raise ValueError('Image must be real-valued numeric pixels')
    if not np.all(np.isfinite(arr)):
        raise ValueError('Image contains non-finite values; clean explicitly')
    if arr.ndim!=2 or min(arr.shape)<16:raise ValueError('Expected a 2D image at least 16x16 pixels')
    # RosettaSciIO axes entries use index_in_array (not presentation order).
    indices=(full.ndim-2,full.ndim-1)
    ad={int(ax.get('index_in_array')):ax for ax in dataset.get('axes',[]) if isinstance(ax.get('index_in_array'),(int,np.integer))}
    ay=ad.get(indices[0],{})
    ax=ad.get(indices[1],{})
    sy=nm_scale(ay);sx=nm_scale(ax)
    if sx is None or sy is None:
        calibration='missing_or_unsupported_units'
        sx=sy=None
    else:
        calibration='calibrated'
    info=dict(dataset_index=index,frame_index=frame,raw_dtype=str(full.dtype),
              raw_shape=list(full.shape),shape=list(arr.shape),
              x_nm_per_px=sx,y_nm_per_px=sy,calibration_status=calibration,
              spatial_axes={'y':ay,'x':ax},
              metadata=dataset.get('metadata',{}))
    return arr,info


def load_dm(path: str | Path, dataset_index: int | None = None, frame: int | None = None) -> tuple[np.ndarray,dict]:
    path=Path(path)
    dm_header_version(path)
    try:
        from rsciio.digitalmicrograph import file_reader
    except ImportError as e:
        raise RuntimeError('DM3/DM4 requires: pip install rosettasciio') from e
    ds=file_reader(str(path),lazy=False)
    arr,meta=select_dataset(ds,dataset_index,frame)
    meta['source_name']=path.name
    meta['dm_version']=dm_header_version(path)
    meta['datasets']=inspect_datasets(ds)
    return arr,meta


def robust_preview(image:np.ndarray) -> np.ndarray:
    """Return float32 0-1 for ML/display, *without altering original pixels*."""
    raw=np.asarray(image,dtype=np.float32)
    lo,hi=np.percentile(raw,[0.5,99.5])
    if hi <= lo:return np.zeros_like(raw,dtype=np.float32)
    return np.clip((raw-lo)/(hi-lo),0,1).astype(np.float32)


def area_diameter_nm(area_pixels: int | float, sx:float|None,sy:float|None) -> float|None:
    return 2*math.sqrt(float(area_pixels)*sx*sy/math.pi) if sx is not None and sy is not None else None


def resize_scale(meta:dict, original_shape:tuple[int,int], new_shape:tuple[int,int])->dict:
    """Account for downsampling without silently assuming the x/y factors match."""
    m=dict(meta)
    if m['x_nm_per_px'] is not None and m['y_nm_per_px'] is not None:
        m['x_nm_per_px']*=original_shape[1]/new_shape[1]
        m['y_nm_per_px']*=original_shape[0]/new_shape[0]
    m['analysis_shape']=list(new_shape)
    return m


def json_safe(obj):
    if isinstance(obj,dict):return {str(k):json_safe(v) for k,v in obj.items()}
    if isinstance(obj,(list,tuple)):return [json_safe(v) for v in obj]
    if isinstance(obj,np.generic):return obj.item()
    if isinstance(obj,np.ndarray):return {'shape':list(obj.shape),'dtype':str(obj.dtype)}
    if isinstance(obj,(str,int,float,bool)) or obj is None:return obj
    return str(obj)
