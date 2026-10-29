#!/usr/bin/env python3
"""serial_console.py — Mac-side serial console for blink_ota_esp8266_v36.

The v36 firmware speaks one command per line at 115200 baud and prints a
"[HB] <millis>" heartbeat every 500 ms, so a plain read/send loop is the
whole workflow.

Usage:
  python3 tools/serial_console.py                 # monitor output (30 s)
  python3 tools/serial_console.py -c stat         # send one command
  python3 tools/serial_console.py -c "dcm:ramp 80 5000" -c "dcm:off"
  python3 tools/serial_console.py -t 15           # monitor for 15 s
  python3 tools/serial_console.py -p /dev/cu.usbserial-DN05I0TZ -c stat

Options:
  -p PORT   serial port (default: autodetect the first /dev/cu.usb*)
  -b BAUD   baud rate (default 115200)
  -c CMD    command to send; repeatable, sent in order (quote multi-word ones)
  -t SEC    seconds to listen: after each command (default 5), or the whole
            monitor window when no commands are given (default 30)

Requires pyserial:  pip3 install --user pyserial

Note: opening the port can pulse DTR/RTS and reset the board through its
auto-reset circuit — a boot banner right after connect is normal, not a fault.
"""
import argparse
import glob
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial is required:  pip3 install --user pyserial")


def find_port():
    ports = sorted(glob.glob("/dev/cu.usb*"))
    return ports[0] if ports else None


def pump(ser, seconds, t0_ref=None):
    """Print every line arriving within the window; [HB] lines included."""
    t_end = time.time() + seconds
    while time.time() < t_end:
        line = ser.readline().decode(errors="replace").rstrip()
        if line:
            stamp = "" if t0_ref is None else "%6.1fs " % (time.time() - t0_ref)
            print(stamp + line, flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-p", "--port", help="serial port (default: first /dev/cu.usb*)")
    ap.add_argument("-b", "--baud", type=int, default=115200)
    ap.add_argument("-c", "--cmd", action="append", default=[],
                    help='command to send, e.g. -c "dcm:ramp 80 5000" (repeatable)')
    ap.add_argument("-t", "--seconds", type=float, default=None,
                    help="listen window: per command (default 5) / monitor (default 30)")
    args = ap.parse_args()

    port = args.port or find_port()
    if not port:
        sys.exit("no /dev/cu.usb* port found — plug the data-capable USB cable")
    print("port: %s @ %d" % (port, args.baud), flush=True)

    ser = serial.Serial(port, args.baud, timeout=0.5)
    ser.reset_input_buffer()  # drop stale bytes from before our open

    if not args.cmd:
        pump(ser, args.seconds if args.seconds is not None else 30)
    else:
        wait = args.seconds if args.seconds is not None else 5
        for cmd in args.cmd:
            print(">>> %s" % cmd, flush=True)
            ser.write((cmd + "\n").encode())
            ser.flush()
            pump(ser, wait)

    ser.close()


if __name__ == "__main__":
    main()
