"""Compare home pixels outside the floating navigation and its shadow."""
import json, math, os
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw
root=Path(os.environ.get('COMPARISON_DIR','/workspace/work/ui521-comparison'))
report=json.loads((root/'geometry.json').read_text())
for width in [375,390,430]:
    for position in ['top','end']:
        images=[Image.open(root/f'{width}-{position}-{v}.png').convert('RGB') for v in ['before','after']]
        navs=[r['nav'] for r in report if r.get('position')==position and r['width']==width]
        # Navigation geometry, blur and soft shadow are the only allowed visual changes.
        box=(math.floor(min(n['x'] for n in navs)-36),math.floor(min(n['y'] for n in navs)-36),math.ceil(max(n['x']+n['width'] for n in navs)+36),math.ceil(max(n['y']+n['height'] for n in navs)+36))
        for image in images: ImageDraw.Draw(image).rectangle(box,fill=(0,0,0))
        diff=ImageChops.difference(*images)
        assert diff.getbbox() is None, f'{width}/{position}: home changed outside navigation/shadow: {diff.getbbox()}'
        print(f'PASS {width}px {position}: zero changed pixels outside navigation/shadow')
