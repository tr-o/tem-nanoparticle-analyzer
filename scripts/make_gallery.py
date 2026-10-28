"""Build Markdown-friendly image grids of synthetic training and test data."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[1]
out = root/'docs'
out.mkdir(exist_ok=True)

def make_grid(split, count, cols):
    tile_w, tile_h = 246, 152
    rows = (count+cols-1)//cols
    sheet = Image.new('RGB',(cols*tile_w,rows*tile_h),(245,246,247))
    draw = ImageDraw.Draw(sheet)
    for i in range(count):
        name = f'{split}_{i:02d}'
        img = Image.open(root/'demo_data'/split/'images'/f'{name}.png').convert('RGB')
        mask = Image.open(root/'demo_data'/split/'masks'/f'{name}.png').convert('RGB')
        img.thumbnail((116,116))
        mask.thumbnail((116,116))
        x,y = (i%cols)*tile_w,(i//cols)*tile_h
        sheet.paste(img,(x+4,y+25))
        sheet.paste(mask,(x+125,y+25))
        draw.text((x+4,y+4),f'{name} | image / GT mask',fill=(25,30,40))
    sheet.save(out/f'{split}_contact_sheet.jpg',quality=87,optimize=True)

make_grid('train',16,4)
make_grid('test',4,2)
analysis = root/'results/test_00/overview.png'
if analysis.exists():
    with Image.open(analysis) as im:
        im.thumbnail((1500,800))
        im.convert('RGB').save(out/'analysis_overview.jpg',quality=88,optimize=True)
