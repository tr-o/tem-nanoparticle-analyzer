"""Inspect raw DM3/DM4 datasets/calibration without running nanoparticle ML."""
import argparse, json
from pathlib import Path
from dm_io import dm_header_version,inspect_datasets,select_dataset,json_safe

def inspect(path):
    from rsciio.digitalmicrograph import file_reader
    dm_header_version(path)
    datasets=file_reader(str(path),lazy=False)
    options=inspect_datasets(datasets)
    selections=[]
    for i,d in enumerate(datasets):
        if len(d['data'].shape)==2:
            _,m=select_dataset(datasets,index=i)
            selections.append(dict(index=i,shape=m['shape'],dtype=m['raw_dtype'],
                  x_nm_per_px=m['x_nm_per_px'],y_nm_per_px=m['y_nm_per_px'],
                  calibration_status=m['calibration_status']))
    return {'source_name':Path(path).name,'dm_version':dm_header_version(path),'datasets':options,'two_dimensional_images':selections}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('image');p.add_argument('--out');a=p.parse_args()
    d=inspect(a.image)
    if a.out:Path(a.out).write_text(json.dumps(json_safe(d),indent=2))
    print(json.dumps(json_safe(d),indent=2))
