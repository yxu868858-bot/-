"""把 index.html 及 assets/img 下的图片打包为一个可独立分享的单文件 HTML。

每张图以 base64 形式只存放一次（window.IMG），页面脚本中的 img() 会优先读取它。
"""
import base64, json, pathlib

root = pathlib.Path(__file__).parent
html = (root / 'index.html').read_text(encoding='utf-8')
imgs = {p.stem: 'data:image/jpeg;base64,' + base64.b64encode(p.read_bytes()).decode()
        for p in sorted((root / 'assets' / 'img').glob('*.jpg'))}

marker = '<script>\n(() => {'
assert html.count(marker) == 1
html = html.replace(marker, '<script>window.IMG=' + json.dumps(imgs) + ';</script>\n' + marker)

dist = root / 'dist'
dist.mkdir(exist_ok=True)
target = dist / '义巷漫游集-动态汇报.html'
target.write_text(html, encoding='utf-8')
print(f'{target} {target.stat().st_size / 1e6:.1f} MB, {len(imgs)} images')
