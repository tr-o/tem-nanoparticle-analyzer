"""Fetch ONLY externally licensed, attributed TEM figures to the reference folder."""
from pathlib import Path
from urllib.request import Request, urlopen

URL = ('https://media.springernature.com/lw685/springer-static/image/'
       'art%3A10.1038%2Fsrep40103/MediaObjects/'
       '41598_2017_Article_BFsrep40103_Fig2_HTML.jpg')
TARGET = Path(__file__).resolve().parents[1]/'reference_tem/08_AuPt_srep40103_fig2.jpg'

if __name__ == '__main__':
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    request = Request(URL, headers={'User-Agent': 'Mozilla/5.0 (TEM research attribution demo)'})
    try:
        with urlopen(request, timeout=30) as response:
            blob = response.read()
        if not (blob.startswith(b'\xff\xd8') or blob.startswith(b'\x89PNG')):
            raise ValueError('The downloaded content was not a JPEG/PNG figure')
        TARGET.write_bytes(blob)
        print('Downloaded licensed research figure:', TARGET, len(blob), 'bytes')
    except Exception as exc:
        print('Licensed reference image could not be retrieved:', exc)
        # This image is optional and must not block generation of the actual dataset.
