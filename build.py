"""把 index.html 及其引用的 assets/img 图片内联为一个可独立分享的单文件 HTML。

同一张图在页面中会被多处引用，因此每张图只以 base64 形式存放一次（IMG 字典），
再由一小段脚本在加载时填回 <img>、背景图和动态生成的页面中。
"""
import base64, json, pathlib, re

root = pathlib.Path(__file__).parent
html = (root / 'index.html').read_text(encoding='utf-8')
names = sorted(set(re.findall(r'assets/img/([\w-]+)\.jpg', html)))
img = {n: 'data:image/jpeg;base64,' + base64.b64encode((root / f'assets/img/{n}.jpg').read_bytes()).decode()
       for n in names}

html = re.sub(r'src="assets/img/([\w-]+)\.jpg"', r'data-img="\1"', html)
html = re.sub(r'style="background-image:url\(assets/img/([\w-]+)\.jpg\);?', r'data-bg="\1" style="', html)
html = re.sub(r"'assets/img/([\w-]+)\.jpg'", r'IMG["\1"]', html)
assert 'assets/img/' not in html, 'unhandled image reference'

loader = ('<script>const IMG=' + json.dumps(img) + ';\n'
          'document.querySelectorAll("[data-img]").forEach(e=>e.src=IMG[e.dataset.img]);\n'
          'document.querySelectorAll("[data-bg]").forEach(e=>e.style.backgroundImage="url("+IMG[e.dataset.bg]+")");'
          '</script>\n<script>\n(() => {')
assert html.count('<script>\n(() => {') == 1
html = html.replace('<script>\n(() => {', loader)

dist = root / 'dist'
dist.mkdir(exist_ok=True)
target = dist / '义巷漫游集-动态汇报.html'
target.write_text(html, encoding='utf-8')
print(f'{target} {target.stat().st_size / 1e6:.1f} MB, {len(names)} images')
