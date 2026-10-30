#!/usr/bin/env python3
"""Fetch an exact, SHA256-verified public Dryad HRTEM image/GT pair.

The dataset is large: never download the whole repository; resolve the
published version and exact filename through the REST API with pagination.
No fixed, unverified file IDs. Failure is explicit, never a fake fixture.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, time
from pathlib import Path
from urllib.parse import quote, urljoin
import requests

BASE = "https://datadryad.org"
DOI = "doi:10.7941/D1SP93"
PREFIX = "Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_"
PAIR = (PREFIX+"Images.h5", PREFIX+"Labels.h5")
MAX_TOTAL = 330_000_000


def absolute(href: str) -> str:
    if not href: raise ValueError("missing Dryad HAL link")
    url = urljoin(BASE,href)
    if not url.startswith(BASE+"/"):
        raise ValueError("Dryad download URL outside allowed host: "+url)
    return url


def get_json(session, url):
    r=session.get(absolute(url),timeout=(25,60),headers={"Accept":"application/json"})
    r.raise_for_status()
    data=r.json()
    if not isinstance(data,dict): raise ValueError("expected JSON dictionary")
    return data


def file_catalog(session, doi=DOI):
    encoded=quote(doi,safe="")
    info=get_json(session,f"/api/v2/datasets/{encoded}")
    version=info["_links"]["stash:version"]["href"]
    v=get_json(session,version)
    url=absolute(v["_links"]["stash:files"]["href"])
    files=[]; visited=set()
    while url:
        if url in visited: raise ValueError("circular Dryad pagination")
        visited.add(url)
        result=get_json(session,url)
        page=result.get("_embedded",{}).get("stash:files",[])
        if not isinstance(page,list): raise ValueError("invalid file listing")
        files.extend(page)
        next_item=result.get("_links",{}).get("next")
        url=absolute(next_item["href"]) if next_item else None
    declared=result.get("total") # optional: last page or current page
    return files,info,v


def select_pair(files, pair=PAIR):
    selected=[]
    for basename in pair:
        matched=[f for f in files if f.get("path","").split("/")[-1]==basename]
        if len(matched)!=1:raise ValueError(f"Expected one matching file {basename}; got {len(matched)}")
        f=matched[0]
        if not str(f.get("mimeType","")).startswith(("application/","")):
            pass
        if f.get("size",0)<1_000_000:raise ValueError("Unreasonable small HDF5: "+basename)
        selected.append(f)
    if sum(f["size"] for f in selected)>MAX_TOTAL:
        raise ValueError("Selected files exceed explicit transfer cap")
    return selected


def download(session, f, dest, attempts=2):
    href=f["_links"]["stash:download"]["href"]
    url=absolute(href)
    expected=f.get("digest")
    digest_type=f.get("digestType","sha-256").lower()
    if digest_type not in ("sha-256","sha256"):
        raise ValueError("No trusted SHA-256 digest for "+f["path"])
    for retry in range(attempts):
        tmp=dest.with_suffix(dest.suffix+".partial")
        tmp.unlink(missing_ok=True)
        try:
            with session.get(url,stream=True,timeout=(30,120),allow_redirects=True,
                headers={"Accept":"application/octet-stream"}) as r:
                r.raise_for_status()
                content_type=r.headers.get("Content-Type","").lower()
                if "text/html" in content_type:raise ValueError("Dryad returned HTML, not HDF5")
                h=hashlib.sha256();n=0
                with tmp.open("wb") as out:
                    for chunk in r.iter_content(chunk_size=2**20):
                        if not chunk:continue
                        out.write(chunk);h.update(chunk);n+=len(chunk)
                        if n>f["size"]+2048:raise ValueError("Downloaded data larger than claimed")
            if n!=f["size"]:raise ValueError(f"File size mismatch expected {f['size']} received {n}")
            if not expected or h.hexdigest().lower()!=expected.lower():
                raise ValueError(f"SHA256 mismatch for {f['path']}")
            if tmp.open("rb").read(8)!=b"\x89HDF\r\n\x1a\n":
                raise ValueError("Not an HDF5 signature")
            tmp.replace(dest)
            return {"filename":dest.name,"size":n,"sha256":h.hexdigest(),"source":url}
        except Exception:
            tmp.unlink(missing_ok=True)
            if retry==attempts-1:raise
            time.sleep(2+retry)


def fetch(out):
    folder=Path(out);folder.mkdir(parents=True,exist_ok=True)
    with requests.Session() as session:
        session.headers.update({"User-Agent":"tem-nanoparticle-analyzer-scientific-data/1.0"})
        files,record,version=file_catalog(session)
        selected=select_pair(files)
        results=[download(session,f,folder/f["path"].split("/")[-1]) for f in selected]
    manifest={"doi":DOI,"version_number":version.get("versionNumber"),"file_listed_count":len(files),
              "files":results,"method":"Dryad API exact-name resolution + SHA256 verification"}
    (folder/"download_manifest.json").write_text(json.dumps(manifest,indent=2))
    return manifest

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out",default="/tmp/lbnl_gt")
    a=p.parse_args();print(json.dumps(fetch(a.out),indent=2))
