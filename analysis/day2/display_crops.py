#!/usr/bin/env python3
"""display_crops.py — montage of the kitchen-balance display at fixed steps inside each command phase.

The TANITA KJ-212 has no data output, so its 7-segment display was read by eye from these montages
(the readings are in twin/data/reverse_IMG_5779.json, boot_thrust_IMG_5781.json, thrust_steps_IMG_5785.json).
The crop box is for the portrait 1080x1920 framing used on day 2 (balance at the bottom of the frame).

Usage:
  python3 analysis/day2/display_crops.py IMG_5785.MOV twin/data/thrust_steps3_hostlog.json 6.74 out.jpg \
      [--from-end 4.0] [--step 0.5] [--box 1420 1740 180 540]
"""
import argparse
import json

import cv2
import numpy as np


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("video")
    ap.add_argument("hostlog")
    ap.add_argument("offset", type=float, help="video = host + offset (s), from sync_audio.py")
    ap.add_argument("out")
    ap.add_argument("--from-end", type=float, default=4.0, help="sample the last N s of each phase (settled part)")
    ap.add_argument("--step", type=float, default=0.5)
    ap.add_argument("--box", nargs=4, type=int, default=(1420, 1740, 180, 540), help="y0 y1 x0 x1 of the display")
    args = ap.parse_args()
    log = json.load(open(args.hostlog))
    tx = [(t, c) for t, k, c in log if k == "tx" and c.startswith("dcm:")]
    v = cv2.VideoCapture(args.video)
    fps = v.get(cv2.CAP_PROP_FPS)
    want = {}
    for (t0, c0), (t1, _) in zip(tx, tx[1:]):
        lab = c0.replace("dcm:speed ", "").replace("dcm:", "")
        for s in np.arange(t1 - args.from_end, t1 - 0.2, args.step):
            want[int(round((s + args.offset) * fps))] = (lab, s + args.offset)
    y0, y1, x0, x1 = args.box
    crops, i = [], 0
    ok, f = v.read()
    while ok:
        if i in want:
            lab, s = want[i]
            c = cv2.resize(f[y0:y1, x0:x1], None, fx=0.28, fy=0.28)
            c = cv2.copyMakeBorder(c, 20, 0, 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
            cv2.putText(c, "%s %.1f" % (lab, s), (2, 15), 0, 0.42, (0, 0, 255), 1)
            crops.append(c)
        ok, f = v.read()
        i += 1
    cols = 8
    while len(crops) % cols:
        crops.append(np.full_like(crops[0], 255))
    cv2.imwrite(args.out, np.vstack([np.hstack(crops[k:k + cols]) for k in range(0, len(crops), cols)]))
    print("wrote %s (%d crops)" % (args.out, len(crops)))


if __name__ == "__main__":
    main()
