#!/usr/bin/env python3
"""README 用: フレーム列(1 本または左右 2 本)を animated WebP にまとめる(img2webp が必要)。

  python3 compose.py out.webp <fps> <height> <dirA> [dirB] [--label-a 文字] [--label-b 文字]
"""
import argparse, glob, os, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont

p = argparse.ArgumentParser()
p.add_argument("out"); p.add_argument("fps", type=float); p.add_argument("height", type=int)
p.add_argument("dirs", nargs="+"); p.add_argument("--label-a"); p.add_argument("--label-b")
p.add_argument("-q", type=int, default=68)
a = p.parse_args()
font = ImageFont.truetype("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc", max(14, a.height // 22))
seqs = [sorted(glob.glob(os.path.join(d, "f*.*"))) for d in a.dirs]
n = min(len(s) for s in seqs)
tmp = tempfile.mkdtemp(); paths = []
for i in range(n):
    ims = []
    for s in seqs:
        im = Image.open(s[i]).convert("RGB")
        ims.append(im.resize((round(im.width * a.height / im.height) // 2 * 2, a.height), Image.LANCZOS))
    gap = 8 if len(ims) > 1 else 0
    canvas = Image.new("RGB", (sum(x.width for x in ims) + gap * (len(ims) - 1), a.height), "white")
    x = 0; dr = ImageDraw.Draw(canvas)
    for j, im in enumerate(ims):
        canvas.paste(im, (x, 0))
        lab = [a.label_a, a.label_b][j] if j < 2 else None
        if lab:
            tw = dr.textlength(lab, font=font); pad = 6
            dr.rectangle([x + 8, 8, x + 8 + tw + 2 * pad, 8 + font.size + 2 * pad], fill=(0, 0, 0))
            dr.text((x + 8 + pad, 8 + pad - 2), lab, font=font, fill="white")
        x += im.width + gap
    pth = os.path.join(tmp, f"{i:04d}.png"); canvas.save(pth); paths.append(pth)
d = str(round(1000 / a.fps))
args = ["img2webp", "-loop", "0", "-lossy", "-q", str(a.q), "-m", "6", "-d", d] + paths + ["-o", a.out]
subprocess.run(args, check=True, capture_output=True)
print(a.out, n, "frames", canvas.size, os.path.getsize(a.out) // 1024, "KB")
