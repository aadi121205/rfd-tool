#!/usr/bin/env python3
"""Read/write SiK (RFD900X2) radio settings over serial.

  rfdtool.py info
  rfdtool.py dump [--remote] [-o file.json]
  rfdtool.py set S3=25 S4=20 [--remote]     (saves + reboots unless --no-save)
  rfdtool.py restore file.json [--remote]
"""
import argparse
import json
import re
import sys
import time

import serial

PORT = "/dev/ttyUSB0"
BAUD = 57600
READ_ONLY = {"S0"}
LINE = re.compile(r"^(S\d+):(\w+)=(-?\d+)")


class Radio:
    def __init__(self, port, baud, remote=False):
        self.ser = serial.Serial(port, baud, timeout=1.5)
        self.prefix = "RT" if remote else "AT"

    def enter_command_mode(self, tries=3):
        # already in command mode (e.g. an earlier session didn't send ATO)?
        self.ser.reset_input_buffer()
        self.ser.write(b"ATI\r")
        time.sleep(0.5)
        if b"SiK" in self.ser.read(128):
            return
        for _ in range(tries):
            self.ser.reset_input_buffer()
            time.sleep(1.2)
            self.ser.write(b"+++")
            time.sleep(1.2)
            if b"OK" in self.ser.read(64):
                return
        sys.exit("radio did not enter command mode (is something else using the port?)")

    def cmd(self, text, wait=0.5):
        self.ser.reset_input_buffer()
        self.ser.write(text.encode() + b"\r")
        time.sleep(wait)
        return self.ser.read(4096).decode(errors="replace")

    def at(self, body, wait=0.5):
        # "ATI5" -> "RTI5" when talking to the remote radio
        return self.cmd(self.prefix + body, wait=wait * (3 if self.prefix == "RT" else 1))

    def params(self):
        out = {}
        for line in self.at("I5", wait=1.0).splitlines():
            m = LINE.match(line.strip())
            if m:
                out[m.group(1)] = {"name": m.group(2), "value": int(m.group(3))}
        if not out:
            sys.exit("no parameters returned (remote radio out of range?)")
        return out

    def set(self, reg, value):
        reply = self.at(f"{reg}={value}")
        if "OK" not in reply:
            sys.exit(f"{reg}={value} rejected: {reply.strip()!r}")

    def save_and_reboot(self):
        self.at("&W")
        self.at("Z")

    def close(self):
        self.cmd("ATO")
        self.ser.close()


def show(params):
    for reg, p in sorted(params.items(), key=lambda kv: int(kv[0][1:])):
        print(f"{reg:>4}  {p['name']:<18} {p['value']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("command", choices=["info", "dump", "set", "restore"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--port", default=PORT)
    ap.add_argument("--baud", type=int, default=BAUD)
    ap.add_argument("--remote", action="store_true", help="talk to the remote radio via RT commands")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("-o", "--output")
    a = ap.parse_args()

    r = Radio(a.port, a.baud, a.remote)
    r.enter_command_mode()
    try:
        if a.command == "info":
            for c in ("I", "I1", "I2", "I3", "I4"):
                print(f"{r.prefix}{c}: {r.at(c).strip().splitlines()[-1] if r.at(c).strip() else ''}")
            return
        if a.command == "dump":
            params = r.params()
            if a.output:
                with open(a.output, "w") as f:
                    json.dump(params, f, indent=2)
                print(f"saved {len(params)} parameters to {a.output}")
            show(params)
            return
        if a.command == "set":
            changes = dict(x.upper().split("=", 1) for x in a.args)
        else:
            with open(a.args[0]) as f:
                saved = json.load(f)
            changes = {k: str(v["value"]) for k, v in saved.items() if k not in READ_ONLY}
        current = r.params()
        for reg, val in changes.items():
            if reg not in current:
                sys.exit(f"unknown register {reg}")
            if str(current[reg]["value"]) != val:
                print(f"{reg} {current[reg]['name']}: {current[reg]['value']} -> {val}")
                r.set(reg, val)
        if not a.no_save:
            r.save_and_reboot()
            print("saved and rebooted")
    finally:
        if a.command in ("info", "dump") or a.no_save:
            r.close()


if __name__ == "__main__":
    main()
