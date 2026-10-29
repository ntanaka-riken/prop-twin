#!/usr/bin/env python3
"""run_sequence.py — send a timed command sequence to the v36 rig and log host times (for filmed runs).

Each command is preceded by the Mac "Tink" sound (audio sync in the video) and the sync LED blinks on
every dcm:* ACK. Host send / receive times go to a JSON log in the same format as twin/data/*_hostlog.json:
  [[t, "beep", null], [t, "tx", cmd], [t, "rx", line], ...]   (t = seconds since the script started)

Opening the port can reset the board (auto-reset), which re-arms the boot sequence (motor starts 5 s
later), so "dcm:auto 0" is always sent first.

Usage:
  python3 tools/run_sequence.py --preset reverse --log twin/data/reverse_hostlog.json --dry-run
  python3 tools/run_sequence.py --preset reverse --log twin/data/reverse_hostlog.json
"""
import argparse
import glob
import json
import subprocess
import sys
import time

TINK = "/System/Library/Sounds/Tink.aiff"


def reverse_preset():
    """Forward / reverse alternation on the balance. The rotor always coasts to a stop (5 s >> 0.75 s)
    before the direction changes: no plugging."""
    seq, t = [], 10.0                                    # 10 s balance baseline first
    for _ in range(3):                                   # 100 %: +, -, three times (drift cancels)
        for s in (255, -255):
            seq += [(t, "dcm:speed %d" % s), (t + 6.0, "dcm:off")]
            t += 11.0
    for duty in (204, 153):                              # 80 %, 60 %: kick at 100 % (cold start needs >= 50 %)
        for d in (1, -1):
            seq += [(t, "dcm:speed %d" % (255 * d)), (t + 1.2, "dcm:speed %d" % (duty * d)), (t + 6.2, "dcm:off")]
            t += 11.2
    seq.append((t + 10.0, "stat"))                       # 10 s closing baseline
    return seq


def bare_preset():
    """Propeller off: forward / reverse alternation at 100 %, four times, to measure the motor's own
    direction asymmetry (no-load ~3700 rpm, coast stop ~0.3 s; 4 s off is plenty)."""
    seq, t = [], 5.0
    for _ in range(4):
        for s in (255, -255):
            seq += [(t, "dcm:speed %d" % s), (t + 5.0, "dcm:off")]
            t += 9.0
    seq.append((t + 3.0, "stat"))
    return seq


def thrust_preset():
    """Steady thrust steps on the balance, forward only (TOUT jumper in): 100 -> 80 -> 60 -> 50 -> 40 %,
    6 s each so the kitchen-balance display settles (it lags ~0.5 s), twice. tel:on logs the ADC
    tachometer (TEL lines, 20 per second) for the speed at every duty; the probe costs ~4 % drive."""
    seq, t = [(1.0, "tel:on")], 8.0                      # 8 s balance baseline
    for _ in range(2):
        seq.append((t, "dcm:speed 255"))
        for duty in (204, 153, 127, 102):
            t += 6.0
            seq.append((t, "dcm:speed %d" % duty))
        t += 6.0
        seq.append((t, "dcm:off"))
        t += 8.0                                         # baseline between / after the passes
    seq += [(t, "tel:off"), (t + 0.5, "stat")]
    return seq


PRESETS = {"reverse": reverse_preset, "bare": bare_preset, "thrust": thrust_preset}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--preset", choices=sorted(PRESETS), required=True)
    ap.add_argument("--log", required=True, help="host log JSON to write")
    ap.add_argument("-p", "--port", help="serial port (default: first /dev/cu.usbserial*)")
    ap.add_argument("--dry-run", action="store_true", help="print the sequence and exit")
    args = ap.parse_args()
    seq = PRESETS[args.preset]()
    if args.dry_run:
        for t, c in seq:
            print("%6.1f s  %s" % (t, c))
        print("total %.0f s" % seq[-1][0])
        return
    import serial
    port = args.port or (sorted(glob.glob("/dev/cu.usbserial*")) or [None])[0]
    if not port:
        sys.exit("no /dev/cu.usbserial* port")
    ser = serial.Serial(port, 115200, timeout=0.02)
    t0 = time.time()
    log = []

    def now():
        return round(time.time() - t0, 4)

    def send(c, beep=True):
        if beep:
            subprocess.Popen(["afplay", TINK])
            log.append([now(), "beep", None])
        ser.write((c + "\n").encode())
        ser.flush()
        log.append([now(), "tx", c])
        print("%7.2f  >>> %s" % (log[-1][0], c), flush=True)

    def pump(until):
        while time.time() - t0 < until:
            line = ser.readline().decode(errors="replace").strip()
            if line and not line.startswith("[HB]"):
                log.append([now(), "rx", line])
                print("%7.2f  %s" % (log[-1][0], line), flush=True)

    try:
        time.sleep(0.3)
        send("dcm:auto 0", beep=False)
        pump(1.0)
        for t, c in seq:
            pump(t)
            send(c)
        pump(seq[-1][0] + 1.0)
    finally:
        ser.write(b"dcm:off\n")                          # never leave it running
        ser.flush()
        json.dump(log, open(args.log, "w"))
        print("wrote %s (%d events)" % (args.log, len(log)))


if __name__ == "__main__":
    main()
