#!/usr/bin/env python3
"""motor_twin.py — digital twin of the v36 rig: ESP8266 firmware -> L293D -> DC motor -> propeller.

Three layers, each mirroring the real thing:
  1. Firmware   : the same command set and ramp engines as blink_ota_esp8266_v36.ino
                  (5 ms loop tick, integer duty math, ramp/step exclusivity, coast/brake).
  2. Electrical : L293D (dual-bridge parallel) + brushed DC motor.
                    drive : 1 kHz PWM resolved per period (see Plant): on = (Vs - V0)
                            across R + rd, off = fast decay through the clamp diodes
                    coast : EN low -> outputs high-Z -> i = 0
                    brake : both outputs HIGH. The L293D high sides only source, so a braking
                            current must loop through one high side and the other output's upper
                            clamp diode into VCC2, costing V_bk (~Vsat + Vf). It flows only while
                            |K w| > V_bk:  L di/dt = -(K w - sgn(w) V_bk) - R i,  i never drives
  3. Mechanical : rotor + propeller
                    J dw/dt = Kt <i> - Tc sgn(w) - b w - Q_aero(w)
                    Q_aero = (kQi(w) + kD kQp(w)) w|w| from the BEMT table (bemt.py, params.json "aero"),
                    or c w|w| when there is no table (propeller off: c = 0, no table)
                    stiction: rotor stays at w = 0 while |Kt i| < Ts (breakaway torque)

Parameters live in params.json (see README.md for which are measured and which are priors).

Usage:
  python3 twin/motor_twin.py                                  # replay the IMG_5741 experiment
  python3 twin/motor_twin.py -s "0:dcm:ramp 80 5000" -s "8:dcm:off" -T 10
  python3 twin/motor_twin.py --boot -T 14                     # boot sequence (5 s: 50->100 %, off at 11 s)
  python3 twin/motor_twin.py --plot out.png                   # also save a plot (matplotlib)
"""
import argparse
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load_params(path=None):
    with open(path or os.path.join(HERE, "params.json")) as f:
        raw = json.load(f)
    P = {k: v["value"] for k, v in raw["params"].items()}
    if "aero" in raw:
        P["aero"] = raw["aero"]
    return P


def aero(P, w):
    """Propeller at w rad/s (sign = direction): signed thrust (N, + = air blown up as forward),
    load torque magnitude (N m), far-wake speed (m/s), signed force the balance sees (N, + = reading rises).
    Reverse (w < 0) blows down onto the cup: its own table ('_r' keys, bemt.py)."""
    A = P.get("aero")
    if not A:
        t = P.get("kT", 0.0) * w * abs(w) if P["c"] > 0 else 0.0
        return t, P["c"] * w * w, 0.0, t
    W = A["w"]
    x = min(abs(w) / (W[1] - W[0]), len(W) - 1.000001)
    k = int(x)
    f = x - k
    suf = "" if w >= 0 or "kT_r" not in A else "_r"

    def lerp(key):
        a = A[key + suf]
        return a[k] + (a[k + 1] - a[k]) * f
    sg = 1.0 if w >= 0 else -1.0
    kD = A["kD"] if w >= 0 else A.get("kD_r", A["kD"])
    return (sg * lerp("kT") * w * w, (lerp("kQi") + kD * lerp("kQp")) * w * w, lerp("kV") * abs(w),
            lerp("kB") * w * w if "kB" in A else sg * lerp("kT") * w * w)


class Firmware:
    """Line-for-line behavioural copy of the v36 dcm:* / rpm:* state machine."""

    TICK = 0.005  # loop() ends with delay(5)
    # closed-loop speed control (same constants as the .ino)
    CTL_MS = 50                    # probe + control period
    PROBE_MS = 2                   # EN low while the back-EMF is read (adc:emf 1500 us + reads)
    CTL_KP, CTL_KI, CTL_ALPHA = 0.04, 0.25, 0.5     # duty/rpm, duty/(rpm s), EMA weight
    RPM_MIN, RPM_MAX = 750.0, 3200.0
    DUTY_FLOOR = 102               # 40 %: below this the motor stalls (adc:emf duty sweep)
    KICK_FRAC = 0.4                # start-up kick at 100 % until the filtered speed passes this
    FF = [(0, 0), (700, 102), (1227, 127), (1629, 153), (2169, 204), (3057, 255)]   # twin steady map
    PROBE_NOISE = 0.20             # commutator ripple seen by a 0.7 ms read: +-20 % uniform (sd 12 %, rpm_ctl_run1)

    def __init__(self, boot_soft_start=False):
        self.duty = 0
        self.dir = 1
        self.on = False
        self.brake = False
        self.ramp = None   # (from, to, ms, start_ms)
        self.step = None   # [target, inc, interval_ms, last_ms]
        self.auto_boot = boot_soft_start
        self.rpm_ctl = False
        self.rpm_ref = self.rpm_filt = self.rpm_meas = self.ctl_i = 0.0
        self.ctl_last = 0
        self.kick_until = -1
        self.probe_until = -1
        self.tel = False
        self.telemetry = []        # (t_ms, duty, rpm_meas, rpm_ref)
        self.w_true = 0.0          # set by simulate() before each tick (the plant's speed)
        import random
        self._rng = random.Random(1)
        self.boot_stage = 0           # 0 armed, 1 running, 2 done/cancelled
        self.log = []

    def _off(self):
        self.on = self.brake = False
        self.ramp = self.step = None
        self.duty = 0

    @classmethod
    def ff_duty(cls, rpm):
        for (r0, d0), (r1, d1) in zip(cls.FF, cls.FF[1:]):
            if rpm <= r1:
                return d0 + (d1 - d0) * (rpm - r0) / (r1 - r0)
        return 255.0

    def command(self, line, now_ms):
        p = line.split()
        if line.startswith("dcm:") and not line.startswith("dcm:auto "):
            self.boot_stage = 2          # manual control cancels the boot sequence
            self.rpm_ctl = False         # ... and the speed controller
        if p and p[0] == "rpm:set" and len(p) == 2:
            ref = float(p[1])
            self.boot_stage = 2
            if ref <= 0:
                self.rpm_ctl = False
                self._off()
            else:
                self.rpm_ref = min(max(ref, self.RPM_MIN), self.RPM_MAX)
                if not self.rpm_ctl:        # fresh reading: rpm_filt may be stale when idle
                    self.ctl_i = 0.0
                    self.rpm_filt = self.rpm_meas = abs(self.w_true) * 30 / math.pi
                self.rpm_ctl = True
                self.ramp = self.step = None
                self.on, self.brake, self.dir = True, False, 1
                if self.rpm_filt < 300:
                    self.kick_until = now_ms + 300
                    self.duty = 255
            self.log.append((now_ms, "ACK " + line))
            return
        if line == "rpm:off":
            self.rpm_ctl = False
            self._off()
            self.log.append((now_ms, "ACK " + line))
            return
        if p and p[0] == "tel:on":
            self.tel = True
            self.log.append((now_ms, "ACK " + line))
            return
        if line == "tel:off":
            self.tel = False
            self.log.append((now_ms, "ACK " + line))
            return
        if line == "dcm:off":
            self._off()
        elif line == "dcm:brake":
            self.ramp = self.step = None
            self.on, self.brake, self.duty = True, True, 0
        elif p[0] == "dcm:speed" and len(p) == 2:
            v = int(p[1])
            self.ramp = self.step = None
            if v == 0:
                self._off()
            else:
                self.dir = 1 if v > 0 else -1
                self.duty = min(abs(v), 255)
                self.on, self.brake = True, False
        elif p[0] == "dcm:ramp" and len(p) == 3:
            pct = max(0, min(100, int(p[1])))
            ms = max(0, min(30000, int(p[2])))
            self.step = None
            self.ramp = (self.duty, pct * 255 // 100, ms, now_ms)
            self.on, self.brake = True, False
        elif p[0] == "dcm:ramp-step" and len(p) == 4:
            pct = max(0, min(100, int(p[1])))
            ms = max(50, min(10000, int(p[2])))
            inc = max(1, min(51, int(p[3])))
            self.ramp = None
            self.step = [pct * 255 // 100, max(1, inc * 255 // 100), ms, now_ms]
            self.on, self.brake = True, False
        elif p[0] == "dcm:auto" and len(p) == 2:
            self.auto_boot = int(p[1]) != 0
            if not self.auto_boot and self.boot_stage == 1:
                self._off()
                self.boot_stage = 2
        else:
            self.log.append((now_ms, "ERR " + line))
            return
        self.log.append((now_ms, "ACK " + line))

    # boot sequence (same constants as the .ino): at 5 s jump to 50 %, ramp to 100 % over 5 s,
    # hold 1 s, coast. Any motion command cancels it.
    BOOT_START_MS, BOOT_FROM_PCT, BOOT_TO_PCT, BOOT_RAMP_MS, BOOT_HOLD_MS = 5000, 50, 100, 5000, 1000

    def control(self, now_ms):
        """Every CTL_MS: probe the back-EMF (EN low PROBE_MS), filter, PI + feedforward."""
        if not (self.rpm_ctl or self.tel) or now_ms - self.ctl_last < self.CTL_MS:
            return
        self.ctl_last = now_ms
        self.probe_until = now_ms + self.PROBE_MS
        noise = 1 + self.PROBE_NOISE * (2 * self._rng.random() - 1)
        self.rpm_meas = abs(self.w_true) * 30 / math.pi * noise
        self.rpm_filt += self.CTL_ALPHA * (self.rpm_meas - self.rpm_filt)
        if self.rpm_ctl:
            if now_ms < self.kick_until and self.rpm_filt < self.KICK_FRAC * self.rpm_ref:
                self.duty = 255
            else:
                e = self.rpm_ref - self.rpm_filt
                ff = self.ff_duty(self.rpm_ref)
                u = ff + self.CTL_KP * e + self.ctl_i
                if self.DUTY_FLOOR < u < 255 or (u >= 255 and e < 0) or (u <= self.DUTY_FLOOR and e > 0):
                    self.ctl_i += self.CTL_KI * e * self.CTL_MS / 1000.0     # anti-windup
                self.duty = int(min(max(ff + self.CTL_KP * e + self.ctl_i, self.DUTY_FLOOR), 255))
            self.on, self.brake, self.dir = True, False, 1
        if self.tel:
            self.telemetry.append((now_ms, self.duty, self.rpm_meas, self.rpm_ref if self.rpm_ctl else 0.0))

    def tick(self, now_ms):
        if self.auto_boot and self.boot_stage == 0 and now_ms >= self.BOOT_START_MS:
            self.boot_stage = 1
            self.step = None
            self.dir, self.duty = 1, self.BOOT_FROM_PCT * 255 // 100
            self.ramp = (self.duty, self.BOOT_TO_PCT * 255 // 100, self.BOOT_RAMP_MS, now_ms)
            self.on, self.brake = True, False
            self.log.append((now_ms, "[DCM] boot sequence start"))
        if self.boot_stage == 1 and now_ms >= self.BOOT_START_MS + self.BOOT_RAMP_MS + self.BOOT_HOLD_MS:
            self.boot_stage = 2
            self._off()
            self.log.append((now_ms, "[DCM] boot sequence done: coast"))
        if self.ramp:
            fr, to, ms, st = self.ramp
            el = now_ms - st
            if el >= ms:
                self.duty, self.ramp = to, None
            elif ms > 0:
                self.duty = fr + (to - fr) * el // ms
        if self.step and now_ms - self.step[3] >= self.step[2]:
            tgt, inc = self.step[0], self.step[1]
            self.step[3] = now_ms
            self.duty = min(self.duty + inc, tgt) if self.duty < tgt else max(self.duty - inc, tgt)
            if self.duty == tgt:
                self.step = None

    def bridge(self, now_ms=None):
        """-> ('coast'|'drive'|'brake', signed duty fraction)."""
        if now_ms is not None and now_ms < self.probe_until:
            return "coast", 0.0          # tachometer probe: EN low
        if not self.on:
            return "coast", 0.0
        if self.brake:
            return "brake", 0.0
        return "drive", self.dir * self.duty / 255.0


def _seg(i0, a, tau, t):
    """Exponential segment i(t) = a + (i0 - a) e^(-t/tau): returns (i(t), integral of i over t)."""
    e = math.exp(-t / tau)
    return a + (i0 - a) * e, a * t + (i0 - a) * tau * (1.0 - e)


def _seg_sq(i0, a, tau, t):
    """Integral of i(t)^2 over the same segment (for copper loss)."""
    e, d = math.exp(-t / tau), i0 - a
    return a * a * t + 2 * a * d * tau * (1 - e) + d * d * tau / 2 * (1 - e * e)


class Plant:
    """L293D + DC motor + propeller. State: current i [A], speed w [rad/s], angle th [rad].

    Stepped once per PWM period (1 kHz on the ESP8266 core). Within a period the speed is
    frozen (tau_mech ~ 0.1 s >> 1 ms) and the current is solved exactly:
      on  (EN high, d*T) : L di/dt = (Vs - V0) - (R + rd) i - K w
      off (EN low)       : outputs Hi-Z, the winding current freewheels through the clamp
                           diodes into VCC2 (fast decay) until it reaches 0, then stays 0:
                           L di/dt = -(Vs + 2 Vf) - R i - K w
    With L/R comparable to the on-time, a low duty delivers far less current than the
    duty-averaged voltage would suggest; IMG_5742 (20 % duty) is what pins L down.
    """

    def __init__(self, P):
        self.P = P
        self.i = 0.0       # current at the end of the last period
        self.im = 0.0      # mean current over the last period (what makes torque)
        self.w = 0.0
        self.th = 0.0
        # period means for display / energy bookkeeping (same definitions as twin.html)
        self.isq = 0.0     # <i^2>
        self.vt = 0.0      # terminal voltage
        self.Psup = self.Pcu = self.Pdrv = self.Pfr = self.Pair = 0.0
        self.thr = self.vw = self.bal = 0.0  # signed thrust (N), far-wake speed (m/s), balance force (N)

    def _drive_period(self, d, T):
        P = self.P
        s = 1.0 if d >= 0 else -1.0
        dd = abs(d)
        R, L, K = P["R"], P["L"], P["K"]
        V0 = P["V0"] + (P.get("dV0_rev", 0.0) if s < 0 else 0.0)   # reverse uses the other L293D halves
        w = s * self.w                   # work in the drive direction
        i = s * self.i
        ton = dd * T
        q = qon = q2on = qoff = q2off = tcond = 0.0
        if ton > 0:
            Ron = R + P["rd"]
            a = (P["Vs"] - V0 - K * w) / Ron
            q2on = _seg_sq(i, a, L / Ron, ton)
            i, qon = _seg(i, a, L / Ron, ton)
        toff = T - ton
        if toff > 0 and i > 0:
            a = -(P["Vs"] + 2 * P["Vf"] + K * w) / R
            tau = L / R
            tz = tau * math.log(1.0 + i / -a) if a < 0 else toff
            tcond = min(tz, toff)
            q2off = _seg_sq(i, a, tau, tcond)
            i, qoff = _seg(i, a, tau, tcond)
            if tcond < toff:
                i = 0.0
        elif toff > 0 and i < 0:
            i = 0.0                      # reverse current cannot persist with EN low
        q = qon + qoff
        self.i = s * i
        self.im = s * q / T
        self.isq = (q2on + q2off) / T
        self.vt = s * ((P["Vs"] - V0) * ton - P["rd"] * qon - (P["Vs"] + 2 * P["Vf"]) * tcond
                       + K * w * (toff - tcond)) / T
        self.Psup = P["Vs"] * (qon - qoff) / T          # fast decay returns energy to VCC2
        self.Pdrv = (V0 * qon + P["rd"] * q2on + 2 * P["Vf"] * qoff) / T
        return s * dd * (P["Vs"] - V0)   # mean applied bridge voltage (for display)

    def step(self, mode, d, T):
        P = self.P
        self.Psup = self.Pdrv = 0.0
        if mode == "coast":
            self.i = self.im = self.isq = 0.0
            self.vt = P["K"] * self.w
            v = 0.0
        elif mode == "drive":
            v = self._drive_period(d, T)
        else:                            # brake: high side + clamp diode loop (see docstring)
            s = 1.0 if self.w >= 0 else -1.0
            emf = P["K"] * abs(self.w)
            a = -(emf - P["V_bk"]) / P["R"] if emf > P["V_bk"] else 0.0
            q2 = _seg_sq(s * self.i, a, P["L"] / P["R"], T) if a < 0 else 0.0
            i, q = _seg(s * self.i, a, P["L"] / P["R"], T)
            if i > 0:                    # diodes block current in the driving direction
                i = 0.0
            self.i, self.im = s * i, s * min(q / T, 0.0)
            self.isq = q2 / T
            self.Pdrv = P["V_bk"] * abs(self.im)
            self.vt = s * P["V_bk"] if a < 0 else P["K"] * self.w
            v = 0.0
        self.Pcu = P["R"] * self.isq
        Tm = P["K"] * self.im
        w = self.w
        if w == 0.0 and abs(Tm) <= P["Ts"]:
            acc = 0.0                    # stuck: stiction holds the rotor
        else:
            sgn = math.copysign(1.0, w if w != 0.0 else Tm)
            Tl = P["Tc"] * sgn + P["b"] * w + math.copysign(aero(P, w)[1], w)
            acc = (Tm - Tl) / P["J"]
        nw = w + acc * T
        if w != 0.0 and nw * w < 0.0 and abs(Tm) <= P["Ts"]:
            nw = 0.0                     # friction can stop the rotor, never reverse it
        self.Pfr = (P["Tc"] if w != 0.0 else 0.0) * abs(w) + P["b"] * w * w
        self.thr, Qa, self.vw, self.bal = aero(P, w)
        self.Pair = Qa * abs(w)
        self.w = nw
        self.th += self.w * T
        return v


def simulate(script, T, P, boot=False, init=None):
    """script: list of (t_seconds, command). init: optional {"w": rad/s} start state.
    Returns dict of time series (one sample per PWM period)."""
    fw = Firmware(boot)
    pl = Plant(P)
    if init:
        pl.w = init.get("w", 0.0)
        if init.get("cmd"):
            fw.command(init["cmd"], 0)
    dt = 1.0 / P["f_pwm"]
    script = sorted(script)
    k = 0
    out = {k_: [] for k_ in ("t", "duty", "mode", "v", "i", "w", "th",
                             "vt", "irms", "Psup", "Pcu", "Pdrv", "Pfr", "Pair", "thr", "vw", "bal")}
    next_tick = 0.0
    n = int(round(T / dt))
    for s in range(n + 1):
        t = s * dt
        now_ms = int(t * 1000 + 1e-9)
        while k < len(script) and script[k][0] <= t + 1e-12:
            fw.command(script[k][1], now_ms)
            k += 1
        if t >= next_tick - 1e-12:
            fw.tick(now_ms)
            next_tick += Firmware.TICK
        fw.w_true = pl.w
        fw.control(now_ms)
        mode, d = fw.bridge(now_ms)
        v = pl.step(mode, d, dt)
        out["t"].append(t); out["duty"].append(fw.duty * fw.dir if fw.on and not fw.brake else 0)
        out["mode"].append(mode); out["v"].append(v); out["i"].append(pl.im)
        out["w"].append(pl.w); out["th"].append(pl.th)
        out["vt"].append(pl.vt); out["irms"].append(math.sqrt(pl.isq))
        for k_ in ("Psup", "Pcu", "Pdrv", "Pfr", "Pair", "thr", "vw", "bal"):
            out[k_].append(getattr(pl, k_))
    out["log"] = fw.log
    out["telemetry"] = fw.telemetry
    return out


IMG_5741 = [(2.817, "dcm:speed 255"), (4.817, "dcm:off")]   # the filmed run (video-synced)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-s", "--step", action="append", default=[],
                    help='timed command "t_sec:command", repeatable')
    ap.add_argument("-T", type=float, default=7.5, help="simulated seconds")
    ap.add_argument("--boot", action="store_true", help="enable the boot sequence (starts at 5 s)")
    ap.add_argument("--params", help="params.json path")
    ap.add_argument("--plot", help="save a PNG plot here")
    args = ap.parse_args()
    P = load_params(args.params)
    script = [(float(s.split(":", 1)[0]), s.split(":", 1)[1]) for s in args.step] or (
        [] if args.boot else IMG_5741)
    r = simulate(script, args.T, P, boot=args.boot)
    for t_ms, msg in r["log"]:
        print("%7.3fs  %s" % (t_ms / 1000, msg))
    stride = max(1, len(r["t"]) // 30)
    print("   t[s]  duty   V[V]   i[A]   rpm")
    for j in range(0, len(r["t"]), stride):
        print("%7.3f %5d %6.2f %6.3f %6.0f" % (r["t"][j], r["duty"][j], r["v"][j], r["i"][j],
                                              r["w"][j] * 60 / (2 * math.pi)))
    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(3, 1, figsize=(9, 7), sharex=True)
        ax[0].plot(r["t"], [x / 255 * 100 for x in r["duty"]]); ax[0].set_ylabel("duty %")
        ax[1].plot(r["t"], r["i"]); ax[1].set_ylabel("current A")
        ax[2].plot(r["t"], [x * 60 / (2 * math.pi) for x in r["w"]]); ax[2].set_ylabel("rpm")
        ax[2].set_xlabel("time s")
        if script is IMG_5741:
            mp = os.path.join(HERE, "data", "IMG_5741_measured.json")
            if os.path.exists(mp):
                m = json.load(open(mp))
                for key, style in (("audio_omega", "C1."), ("video_omega", "C3o")):
                    ax[2].plot([p[0] for p in m[key]], [p[1] * 60 / (2 * math.pi) for p in m[key]],
                               style, ms=4, label=key)
                ax[2].legend()
        plt.tight_layout(); plt.savefig(args.plot, dpi=100)
        print("plot ->", args.plot)


if __name__ == "__main__":
    main()
