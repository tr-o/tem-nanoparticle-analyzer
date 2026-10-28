"""Download properly attributed open-license reference TEM figures.

All third-party images belong in reference_tem/, NEVER demo_data/.
If an origin limits automated access, skip it and keep the source link.
"""
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]/"reference_tem"
FIGURES = {
    "05_Pt_supported_srep44411_fig4.jpg":
        "https://media.springernature.com/lw685/springer-static/image/"
        "art%3A10.1038%2Fsrep44411/MediaObjects/"
        "41598_2017_Article_BFsrep44411_Fig4_HTML.jpg",
    "06_Pt_C_membranes301_fig3.png":
        "https://www.mdpi.com/membranes/membranes-12-00301/article_deploy/html/"
        "images/membranes-12-00301-g003.png",
    "07_Pt_C_nanomaterials3800_fig1.png":
        "https://www.mdpi.com/nanomaterials/nanomaterials-12-03800/article_deploy/html/"
        "images/nanomaterials-12-03800-g001.png",
    "08_AuPt_srep40103_fig2.jpg":
        "https://media.springernature.com/lw685/springer-static/image/"
        "art%3A10.1038%2Fsrep40103/MediaObjects/"
        "41598_2017_Article_BFsrep40103_Fig2_HTML.jpg",
}

def fetch():
    ROOT.mkdir(parents=True, exist_ok=True)
    for name,url in FIGURES.items():
        dest=ROOT/name
        try:
            req=Request(url,headers={
                "User-Agent":"Mozilla/5.0 (compatible; Research dataset documentation)"
            })
            with urlopen(req,timeout=25) as response:
                blob=response.read()
                mime=response.headers.get("Content-Type","")
            if not (blob.startswith(b"\xff\xd8") or blob.startswith(b"\x89PNG")):
                raise ValueError(f"Not a PNG/JPEG figure: {mime}, first bytes={blob[:16]!r}")
            dest.write_bytes(blob)
            print(f"Downloaded open-license figure {dest}: {len(blob)} bytes",flush=True)
        except Exception as exc:
            print(f"NOT SAVED {dest.name}: {exc} (refer to source URL in docs)",flush=True)

if __name__=="__main__":
    fetch()
