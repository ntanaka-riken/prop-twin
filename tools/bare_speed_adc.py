#!/usr/bin/env python3
"""bare_speed_adc.py — propeller-off full speed from the ADC (forward only; TOUT jumper must be in).

  1. dcm:auto 0, adc:zero, adc:read                       (motor stopped)
  2. twice: dcm:speed 255, 3 s, adc:cap 200 4000 500 dcm:off  -> commutator ripple (3 per rev) + coast
  3. dcm:speed 255, 3 s, adc:emf x 6 every 0.5 s, dcm:off       -> back-EMF tachometer
Writes twin/data/adc/bare_coast_{1,2}.json (same format as tools/adc_capture.py) and
twin/data/adc/bare_emf.json (all reply lines).

Usage:  python3 tools/bare_speed_adc.py [--dry-run]
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "twin", "data", "adc")
STEPS = ["dcm:auto 0", "adc:zero", "adc:read",
         "dcm:speed 255", "(3 s)", "adc:cap 200 4000 500 dcm:off", "(3 s stopped)",
         "dcm:speed 255", "(3 s)", "adc:cap 200 4000 500 dcm:off", "(3 s stopped)",
         "dcm:speed 255", "(3 s)", "adc:emf x 6, 0.5 s apart", "dcm:off"]


def main():
    if "--dry-run" in sys.argv:
        print("\n".join(STEPS))
        return
    import serial
    s = serial.Serial("/dev/cu.usbserial-DN05I0TZ", 115200, timeout=0.2)
    log = []

    def cmd(c, w):
        s.write((c + "\n").encode()); s.flush()
        t = time.time() + w; o = []
        while time.time() < t:
            ln = s.readline().decode(errors="replace").strip()
            if ln and not ln.startswith("[HB]"):
                o.append(ln)
        log.append([c, [x for x in o if not (x.startswith("ADC ") and not x.startswith(("ADC cap", "ADC end", "ADC raw")))]])
        print(">>> %s\n    %s" % (c, "\n    ".join(log[-1][1][:8])), flush=True)
        return o

    try:
        time.sleep(0.3); s.reset_input_buffer()
        cmd("dcm:auto 0", 0.5)
        cmd("adc:zero", 1.0)
        cmd("adc:read", 0.5)
        for k in (1, 2):
            cmd("dcm:speed 255", 3.0)
            lines = cmd("adc:cap 200 4000 500 dcm:off", 4.5)
            data = [int(x) for ln in lines if ln.startswith("ADC ") and not ln.startswith(("ADC cap", "ADC end", "ADC raw"))
                    for x in ln[4:].split(",")]
            json.dump({"hdr": [ln for ln in lines if ln.startswith("ADC cap")], "data": data},
                      open(os.path.join(OUT, "bare_coast_%d.json" % k), "w"))
            print("    samples %d" % len(data))
            time.sleep(2.0)
        cmd("dcm:speed 255", 3.0)
        for _ in range(6):
            cmd("adc:emf", 0.5)
        cmd("dcm:off", 0.5)
    finally:
        s.write(b"dcm:off\n"); s.flush(); s.close()
        json.dump(log, open(os.path.join(OUT, "bare_emf.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
