"""把 index.html 及 assets/ 下的图片打包为一个可独立分享的单文件 HTML。

- assets/img/*.jpg 以 base64 存入 window.IMG，页面脚本中的 img() 优先读取；
- assets/layers/layers.js（分析图生长动画的图层清单）连同其中的图片一并内联。
"""
import base64, json, pathlib, re

root = pathlib.Path(__file__).parent
html = (root / 'index.html').read_text(encoding='utf-8')
MIME = {'.jpg': 'image/jpeg', '.webp': 'image/webp', '.png': 'image/png'}


def data_uri(path):
    return f'data:{MIME[path.suffix]};base64,' + base64.b64encode(path.read_bytes()).decode()


layers_js = (root / 'assets' / 'layers' / 'layers.js').read_text(encoding='utf-8')
layered = set(json.loads(layers_js[layers_js.index('{'):layers_js.rindex('}') + 1]))
layers_js = re.sub(r'assets/layers/[\w.-]+', lambda m: data_uri(root / m.group(0)), layers_js)

# 已有图层版本的分析图，单文件中不再重复内嵌其整图
imgs = {p.stem: data_uri(p) for p in sorted((root / 'assets' / 'img').glob('*.jpg')) if p.stem not in layered}

tag = '<script src="assets/layers/layers.js"></script>'
assert html.count(tag) == 1
html = html.replace(tag, '<script>' + layers_js + '</script>\n<script>window.IMG=' + json.dumps(imgs) + ';</script>')

dist = root / 'dist'
dist.mkdir(exist_ok=True)
target = dist / '义巷漫游集-动态汇报.html'
target.write_text(html, encoding='utf-8')
print(f'{target} {target.stat().st_size / 1e6:.1f} MB, {len(imgs)} images + {len(layered)} layered diagrams')
