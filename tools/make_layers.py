"""把方案 PDF 中的分析图拆成"底图 + 逐层叠加"的图层，供汇报页做生长动画。

原理：PDF 页面内容流按绘制顺序排列。把内容流截断到第 k 个对象并渲染，
相邻两次渲染的差异像素就是新画上去的那一层（色块、箭头、标签……）。

输出到 assets/layers/：
  <名称>_base.jpg     底图
  <名称>_<序号>.webp  各叠加层（带透明通道，已裁到自身范围）
  layers.js           图层清单 window.LAYERS

用法：python tools/make_layers.py 方案.pdf
依赖：pymupdf numpy pillow
"""
import io, json, pathlib, re, sys
import numpy as np
import pymupdf
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'assets' / 'layers'

# 名称 -> (页码, 裁切区域[页面比例], 输出宽度 px)；与 make_assets.py 中的区域一致
TARGETS = {
    'map': (4, [0, .19, 1, 1], 2000), 'site': (5, [.03, .13, .98, .605], 2000),
    'traffic': (6, [0, .20, 1, 1], 2000), 'vertical': (7, [0, .19, 1, .80], 2000),
    'buildtype': (8, [0, .12, 1, .78], 2000),
    'layout': (18, [0, .25, 1, .84], 2000), 'function': (19, [0, .25, 1, .85], 2000), 'stylepos': (20, [0, .24, 1, .84], 2000),
    's21a': (21, [0, .30, .515, .92], 1400), 's21b': (21, [.52, .30, 1, .92], 1400),
    's22a': (22, [0, .32, .515, .97], 1400), 's22b': (22, [.52, .32, 1, .97], 1400),
    's23a': (23, [0, .29, .515, .97], 1400), 's23b': (23, [.52, .29, 1, .97], 1400),
    'section': (30, [.03, .10, .62, 1], 1800),
    'wtop': (34, [0, .1, 1, .535], 2000), 'etop': (57, [0, .1, 1, .506], 2000),
    'keyplan': (87, [0, .12, 1, .463], 2000),
    'paving': (89, [.03, .10, .97, .95], 2000),
    'out1': (90, [.01, .17, .99, .83], 2000), 'out2': (91, [.04, .13, .98, .77], 2000),
    'light1': (93, [.04, .10, .97, .43], 2000), 'light2': (93, [.04, .52, .97, .88], 2000),
}
PROBE_W = 500        # 逐步探测时的渲染宽度
DIFF = 10            # 判定像素变化的阈值（0–255）
BIG = .02            # 变化面积超过裁切区 2% 的步骤单独成层
MAX_LAYERS = 14      # 每张图最多保留的叠加层数


def boundaries(c):
    """扫描内容流，返回每个 Q / ET 之后的截断位置及当时的 q 嵌套深度。"""
    out, i, n, depth, in_bt = [], 0, len(c), 0, False
    while i < n:
        ch = c[i]
        if ch == '(':                       # 字符串，含转义与嵌套括号
            d = 0
            while i < n:
                if c[i] == '\\':
                    i += 2
                    continue
                if c[i] == '(':
                    d += 1
                elif c[i] == ')':
                    d -= 1
                    if d == 0:
                        break
                i += 1
            i += 1
            continue
        if ch == '<' and c[i:i + 2] != '<<':  # 十六进制字符串
            i = c.find('>', i) + 1
            continue
        if ch == '%':
            j = c.find('\n', i)
            i = n if j < 0 else j
            continue
        prev = c[i - 1] if i else ' '
        if prev in ' \n\r\t])>':
            if c.startswith('BI', i) and c[i + 2:i + 3] in ' \n\r\t':   # 内嵌图像
                i = c.find('EI', i + 2) + 2
                continue
            m = re.match(r'(BT|ET|q|Q)(?=[\s/\[<(]|$)', c[i:i + 3])
            if m:
                t = m.group(1)
                if t == 'q':
                    depth += 1
                elif t == 'Q':
                    depth -= 1
                    out.append((i + 1, depth, in_bt))
                elif t == 'BT':
                    in_bt = True
                else:
                    in_bt = False
                    out.append((i + 2, depth, False))
                i += len(t)
                continue
        i += 1
    return out


class Stepper:
    def __init__(self, pdf, pno):
        self.doc = pymupdf.open(pdf)
        self.pno = pno
        pg = self.doc[pno - 1]
        self.xrefs = pg.get_contents()
        self.c = b'\n'.join(self.doc.xref_stream(x) for x in self.xrefs).decode('latin1')
        for x in self.xrefs[1:]:
            self.doc.update_stream(x, b' ')
        self.b = boundaries(self.c)
        self.W, self.H = pg.rect.width, pg.rect.height

    def render(self, k, frac, width):
        """渲染截断到第 k 个边界时的画面（RGB 数组）。"""
        pos, depth, in_bt = self.b[k]
        s = self.c[:pos] + (' ET' if in_bt else '') + ' Q' * depth
        self.doc.update_stream(self.xrefs[0], s.encode('latin1'))
        pg = self.doc.reload_page(self.doc[self.pno - 1])
        r = pymupdf.Rect(frac[0] * self.W, frac[1] * self.H, frac[2] * self.W, frac[3] * self.H)
        z = width / r.width
        pix = pg.get_pixmap(matrix=pymupdf.Matrix(z, z), clip=r, alpha=False)
        return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3).copy()


def changed(a, b):
    return np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2) > DIFF


def plan_groups(st, frac):
    """低分辨率逐步渲染，决定底图截止点与叠加层的分组。"""
    frames = [st.render(k, frac, PROBE_W) for k in range(len(st.b))]
    steps = []
    for k in range(1, len(frames)):
        m = changed(frames[k - 1], frames[k])
        if m.mean() > .0004:
            ys, xs = np.nonzero(m)
            box = (xs.min(), ys.min(), xs.max(), ys.max())
            cover = (box[2] - box[0]) * (box[3] - box[1]) / (m.shape[0] * m.shape[1])
            steps.append((k, m.mean(), cover))
    # 底图：直到最后一个覆盖裁切区 70% 以上范围的步骤（大面积背景、底图照片）
    base_k = 0
    for k, area, cover in steps:
        if cover > .7:
            base_k = k
    rest = [s for s in steps if s[0] > base_k]
    # 分组：大面积步骤单独成层，连续的小步骤合并
    groups, small = [], []
    for k, area, cover in rest:
        if area >= BIG:
            if small:
                groups.append(small[-1])
                small = []
            groups.append(k)
        else:
            small.append(k)
            if len(small) >= 6:
                groups.append(small[-1])
                small = []
    if small:
        groups.append(small[-1])
    # 层数过多时合并相邻层
    while len(groups) > MAX_LAYERS:
        groups = groups[1::2] if len(groups) % 2 == 0 else groups[:1] + groups[2::2]
    return base_k, groups, len(frames) - 1


def kind(x, y, w, h, W, H):
    if w * h > .25 * W * H and w > .6 * W and h < .45 * H:
        return 'wipe'                       # 横向长条（如沿街色带）：从左向右展开
    if w * h < .01 * W * H:
        return 'pop'                        # 小图标、小标签：弹出
    return 'grow'                           # 色块：从中心生长


def main(pdf):
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob('*'):
        f.unlink()
    manifest = {}
    for name, (pno, frac, width) in TARGETS.items():
        st = Stepper(pdf, pno)
        base_k, groups, last = plan_groups(st, frac)
        base = st.render(base_k, frac, width)
        Image.fromarray(base).save(OUT / f'{name}_base.jpg', quality=84, optimize=True)
        H, W = base.shape[:2]
        layers, prev = [], base
        for i, k in enumerate(groups):
            cur = st.render(k, frac, width)
            m = changed(prev, cur)
            if m.any():
                m = np.maximum.reduce([m, np.roll(m, 1, 0), np.roll(m, -1, 0), np.roll(m, 1, 1), np.roll(m, -1, 1)])
                ys, xs = np.nonzero(m)
                x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
                rgba = np.dstack([cur, (m * 255).astype(np.uint8)])[y0:y1, x0:x1]
                fn = f'{name}_{i + 1:02d}.webp'
                Image.fromarray(rgba, 'RGBA').save(OUT / fn, quality=90, method=6)
                layers.append({'src': 'assets/layers/' + fn, 'x': int(x0), 'y': int(y0), 'w': int(x1 - x0), 'h': int(y1 - y0),
                               'kind': kind(x0, y0, x1 - x0, y1 - y0, W, H)})
            prev = cur
        # 校验：叠加结果应与完整页面一致
        full = st.render(last, frac, width)
        miss = changed(prev, full).mean()
        manifest[name] = {'w': W, 'h': H, 'base': f'assets/layers/{name}_base.jpg', 'layers': layers}
        print(f'{name:10s} p{pno:<3d} base@{base_k:<3d} layers={len(layers):2d} residual={miss * 100:.2f}%')
    (OUT / 'layers.js').write_text('window.LAYERS=' + json.dumps(manifest, ensure_ascii=False) + ';\n', encoding='utf-8')


if __name__ == '__main__':
    main(sys.argv[1])
