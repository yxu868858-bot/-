"""从方案 PDF 中提取汇报所需的图片素材，输出到 assets/img/。

- 照片 / 效果图：按 PDF 内部对象号直接导出原始 JPEG 字节，不做二次压缩；
- 平面图 / 分析图：按页面区域高分辨率渲染（保留矢量标注）。

用法：python tools/make_assets.py 方案.pdf
依赖：pymupdf
"""
import pathlib, sys
import pymupdf

OUT = pathlib.Path(__file__).resolve().parent.parent / 'assets' / 'img'

# 原图导出：文件名 -> (页码, 对象号)
NATIVE = {
    # 篇章扉页配图
    'div1': (3, 4790), 'div2': (10, 4804), 'div3': (16, 4818), 'div4': (27, 4977), 'div5': (32, 4989), 'div6': (83, 5095),
    # 建筑风格
    'style1': (9, 4798), 'style2': (9, 4800), 'style3': (9, 4799), 'style4': (9, 4801), 'style5': (9, 4802), 'style6': (9, 4803),
    # 案例
    'case1a': (11, 4806), 'case1b': (11, 4805), 'case1c': (11, 4807),
    'case2a': (12, 4810), 'case2b': (12, 4809), 'case2c': (12, 4808),
    'case3a': (13, 4812), 'case3b': (13, 4811), 'case3c': (13, 4813),
    'case4a': (14, 4814), 'case4b': (14, 4816), 'case4c': (14, 4815),
    'sum': (15, 4817), 'pos': (17, 4819),
    'fast1': (24, 4970), 'fast2': (24, 4971), 'fast3': (24, 4972), 'theme': (25, 4974),
    # 片区总览四图
    'w1': (34, 4996), 'w2': (34, 4994), 'w3': (34, 4992), 'w4': (34, 4991),
    'e1': (57, 5051), 'e2': (57, 5049), 'e3': (57, 5047), 'e4': (57, 5045),
    # 植物
    'pc1': (84, 5096), 'pc2': (84, 5097), 'pc3': (84, 5098),
    'pf1': (85, 5100), 'pf2': (85, 5101), 'pf3': (85, 5102),
    'z1': (87, 5131), 'z2': (87, 5132), 'z3': (87, 5133), 'z4': (87, 5134),
    'z5': (88, 5143), 'z6': (88, 5144), 'z7': (88, 5145), 'z8': (88, 5146),
    # 意向
    'pv1': (92, 5178), 'pv2': (92, 5179), 'pv3': (92, 5181), 'pv4': (92, 5180), 'pv5': (92, 5177),
    'li1': (94, 5188), 'li2': (94, 5189), 'li3': (94, 5190), 'li4': (94, 5187),
    'fb1': (95, 5194), 'fb2': (95, 5193), 'fb3': (95, 5191), 'fb4': (95, 5195), 'fb5': (95, 5196),
    'ar1': (96, 5202), 'ar2': (96, 5201), 'ar3': (96, 5199), 'ar4': (96, 5197),
    'ar5': (97, 5204), 'ar6': (97, 5205), 'ar7': (97, 5206),
}
# 整体植物配置：上木 5 + 下木 4 + 地被 18
for i, x in enumerate([5106, 5105, 5104, 5107, 5103, 5109, 5110, 5111, 5112] + list(range(5113, 5131)), 1):
    NATIVE[f'pl{i:02d}'] = (86, x)
# 效果图页：每页最大的那张图
for p in [36, 37, 38, 39, 40, 41, 43, 44, 45, 46, 47, 49, 50, 51, 53, 54, 55, 59, 60, 61,
          63, 64, 65, 66, 67, 68, 70, 71, 73, 74, 77, 78, 80, 81, 82]:
    NATIVE[f'r{p}'] = (p, None)

# 区域渲染：文件名 -> (页码, [x0, y0, x1, y1] 页面比例, 输出宽度 px)
CLIP = {
    'map': (4, [0, .19, 1, 1], 2000), 'site': (5, [.03, .13, .98, .605], 2000),
    'traffic': (6, [0, .20, 1, 1], 2000), 'vertical': (7, [0, .19, 1, .80], 2000),
    'buildtype': (8, [0, .12, 1, .78], 2000),
    'layout': (18, [0, .25, 1, .84], 2000), 'function': (19, [0, .25, 1, .85], 2000), 'stylepos': (20, [0, .24, 1, .84], 2000),
    's21a': (21, [0, .30, .515, .92], 1400), 's21b': (21, [.52, .30, 1, .92], 1400),
    's22a': (22, [0, .32, .515, .97], 1400), 's22b': (22, [.52, .32, 1, .97], 1400),
    's23a': (23, [0, .29, .515, .97], 1400), 's23b': (23, [.52, .29, 1, .97], 1400),
    'lang1': (26, [.04, .33, .31, .95], 900), 'lang2': (26, [.31, .33, .51, .95], 700), 'lang3': (26, [.51, .33, 1, .95], 1400),
    'master': (28, [0, .24, 1, .67], 2200), 'masterlbl': (29, [0, .167, 1, .589], 2200),
    'section': (30, [.03, .10, .62, 1], 1800),
    'wtop': (34, [0, .1, 1, .535], 2000), 'etop': (57, [0, .1, 1, .506], 2000),
    'keyplan': (87, [0, .12, 1, .463], 2000),
    'paving': (89, [.03, .10, .97, .95], 2000),
    'out1': (90, [.01, .17, .99, .83], 2000), 'out2': (91, [.04, .13, .98, .77], 2000),
    'light1': (93, [.04, .10, .97, .43], 2000), 'light2': (93, [.04, .52, .97, .88], 2000),
}
PLANS = {  # 分区平面：平面图区域、索引图区域
    35: ([.046, .098, .427, .969], [.55, .222, .915, .351]),
    42: ([.046, .106, .605, .94], [.621, .277, .987, .406]),
    48: ([.052, .113, .612, .896], [.621, .277, .987, .406]),
    52: ([.046, .114, .617, .888], [.621, .277, .987, .406]),
    58: ([.047, .101, .533, .915], [.556, .277, .922, .406]),
    62: ([.047, .18, .617, .724], [.621, .318, .987, .448]),
    69: ([.048, .095, .545, .941], [.556, .277, .922, .406]),
    72: ([.048, .1, .567, .928], [.606, .277, .971, .406]),
    76: ([.047, .107, .614, .907], [.621, .106, .987, .235]),
    79: ([.023, .276, .987, .613], [.621, .132, .987, .261]),
}
for p, (plan, key) in PLANS.items():
    CLIP[f'plan{p}'] = (p, plan, 1300)
    CLIP[f'key{p}'] = (p, key, 700)


def save_native(doc, name, page, xref):
    if xref is None:
        infos = [i for i in doc[page - 1].get_image_info(xrefs=True) if i['xref']]
        xref = max(infos, key=lambda i: i['width'] * i['height'])['xref']
    info = doc.extract_image(xref)
    path = OUT / f'{name}.jpg'
    if info['ext'] in ('jpeg', 'jpg') and info.get('colorspace') == 3 and not info.get('smask'):
        path.write_bytes(info['image'])
    else:
        pix = pymupdf.Pixmap(doc, xref)
        if pix.alpha or pix.n - pix.alpha != 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            if pix.alpha:
                pix = pymupdf.Pixmap(pix, 0)
        pix.save(str(path), jpg_quality=92)


def save_clip(doc, name, page, frac, width):
    pg = doc[page - 1]
    W, H = pg.rect.width, pg.rect.height
    r = pymupdf.Rect(frac[0] * W, frac[1] * H, frac[2] * W, frac[3] * H) & pg.rect
    zoom = width / r.width
    pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=r, alpha=False)
    pix.save(str(OUT / f'{name}.jpg'), jpg_quality=82)


def main(pdf):
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob('*.jpg'):
        f.unlink()
    doc = pymupdf.open(pdf)
    for name, (page, xref) in NATIVE.items():
        save_native(doc, name, page, xref)
    for name, (page, frac, width) in CLIP.items():
        save_clip(doc, name, page, frac, width)
    print(len(list(OUT.glob('*.jpg'))), 'images ->', OUT)


if __name__ == '__main__':
    main(sys.argv[1])
