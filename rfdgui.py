#!/usr/bin/env python3
"""RFD900 Tools clone for SiK / RFD900X2 radios on Linux."""
import glob
import json
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from rfdtool import Radio

BG = "#f0f0f0"
BTN = "#dcdcdc"
DIM = "#8a8a8a"
FONT = ("DejaVu Sans", 9)

BAUDS = ["1", "2", "4", "9", "19", "38", "57", "115", "230", "460"]
AIRS = ["2", "4", "8", "16", "19", "24", "32", "48", "64", "96", "128", "192", "250"]
POWERS = [str(p) for p in (1, 2, 5, 8, 11, 14, 17, 20, 23, 26, 27, 28, 29, 30)]
MAVLINK = {0: "RawData", 1: "Mavlink", 2: "LowLatency"}
COUNTS = [str(i) for i in (5, 10, 20, 21, 25, 50, 51)]
DUTY = [str(i) for i in range(0, 101, 10)]
LBT = ["0"] + [str(i) for i in range(25, 221, 15)]

# (label, register-name aliases, kind, choices, row, column)
# kinds: ro, combo, mav, check. Fields whose register the radio doesn't report stay greyed out.
FIELDS = [
    ("Format", ["FORMAT"], "ro", None, 3, 0),
    ("Baud", ["SERIAL_SPEED"], "combo", BAUDS, 4, 0),
    ("Air Speed", ["AIR_SPEED"], "combo", AIRS, 5, 0),
    ("Net ID", ["NETID"], "combo", [str(i) for i in range(256)], 6, 0),
    ("Tx Power", ["TXPOWER"], "combo", POWERS, 7, 0),
    ("ECC", ["ECC"], "check", None, 8, 0),
    ("Mavlink", ["MAVLINK"], "mav", None, 9, 0),
    ("Op Resend", ["OPPRESEND", "OP_RESEND"], "check", None, 10, 0),
    ("GPI1_1R/CIN", ["GPI1_1RCIN", "GPI1_1R/CIN"], "check", None, 11, 0),
    ("GPO1_1R/COUT", ["GPO1_1RCOUT", "GPO1_1R/COUT"], "check", None, 12, 0),
    ("GPO1_3SBUSIN", ["GPO1_1SBUSIN", "GPO1_3SBUSIN"], "check", None, 13, 0),
    ("GPO1_3STATLED", ["GPO1_3STATLED"], "check", None, 15, 0),
    ("GPI1_2AUXIN", ["GPI1_2AUXIN"], "check", None, 16, 0),
    ("GPO1_3AUXOUT", ["GPO1_3AUXOUT"], "check", None, 17, 0),
    ("Min Freq", ["MIN_FREQ"], "combo", ["902000", "915000", "868000", "433000"], 3, 2),
    ("Max Freq", ["MAX_FREQ"], "combo", ["928000", "915000", "870000", "435000"], 4, 2),
    ("# of Channels", ["NUM_CHANNELS"], "combo", COUNTS, 5, 2),
    ("Duty Cycle", ["DUTY_CYCLE"], "combo", DUTY, 6, 2),
    ("LBT Rssi", ["LBT_RSSI"], "combo", LBT, 7, 2),
    ("RTS CTS", ["RTSCTS"], "check", None, 8, 2),
    ("Max Window (ms)", ["MAX_WINDOW"], "combo", ["33", "66", "100", "131"], 9, 2),
    ("AES Encryption", ["ENCRYPTION_LEVEL"], "combo", ["0", "128", "256"], 10, 2),
    ("GPO1_0TXEN485", ["GPO1_0TXEN485"], "check", None, 15, 2),
    ("GPIO1_1FUNC", ["GPIO1_1FUNC"], "combo", ["0", "1", "2", "3"], 16, 2),
    ("Antenna Mode", ["ANT_MODE"], "combo", ["0", "1", "2"], 3, 4),
    ("Failsafe Frame Loss", ["FSFRAMELOSS"], "combo", ["0", "10", "50", "100", "200"], 16, 4),
]
COPY_TO_REMOTE = ["Air Speed", "Net ID", "ECC", "Mavlink", "Op Resend", "Min Freq", "Max Freq",
                  "# of Channels", "Duty Cycle", "LBT Rssi", "Max Window (ms)"]


def grey_button(parent, text, command, **kw):
    return tk.Button(parent, text=text, command=command, bg=BTN, activebackground="#cfcfcf", relief="raised",
                     bd=1, font=FONT, **kw)


class Panel(tk.LabelFrame):
    """The Local or Remote half of the settings area."""

    def __init__(self, parent, title, app, local):
        super().__init__(parent, text=title, bg=BG, font=FONT, bd=1, relief="groove")
        self.app = app
        self.params = {}
        self.fields = {}
        self.labels = []
        self.version = tk.StringVar()
        self.rssi = tk.StringVar()

        self._label("Version", 0, 0, sticky="e")
        ttk.Entry(self, textvariable=self.version, state="readonly", width=34).grid(
            row=0, column=1, columnspan=3 if local else 4, sticky="we", padx=2, pady=2)
        if local:
            ttk.Entry(self, state="readonly", width=14).grid(row=0, column=4, sticky="we", padx=2)
        self._label("RSSI", 1, 0, sticky="e")
        tk.Label(self, textvariable=self.rssi, bg="white", bd=1, relief="sunken", font=("DejaVu Sans", 8),
                 anchor="nw", justify="left", height=3, wraplength=330).grid(
            row=1, column=1, columnspan=4, sticky="nswe", padx=2, pady=2, rowspan=2)
        box = tk.Label(self, bg="white", bd=1, relief="sunken", width=8, height=3)
        box.grid(row=0, column=5, rowspan=3, sticky="nswe", padx=2, pady=2)
        self._label("Country:", 0, 6, sticky="w")
        tk.Label(self, bg="white", bd=1, relief="sunken", width=8, height=2).grid(
            row=1, column=6, rowspan=2, sticky="nwe", padx=2)

        for label, aliases, kind, choices, row, col in FIELDS:
            self._field(label, aliases, kind, choices, row, col)

        # widgets that exist in the original but can't be driven on this radio
        self._label("AES Key", 11, 2, sticky="w")
        self.aes_btn = grey_button(self, "Random", lambda: None, width=8, state="disabled")
        self.aes_btn.grid(row=11, column=3, sticky="w", padx=2)
        ttk.Entry(self, state="disabled").grid(row=12, column=2, columnspan=3, sticky="we", padx=2)
        self._label("GPO1_3SBUSOUT:", 12, 5, sticky="w", span=2)
        ttk.Combobox(self, state="disabled", width=9).grid(row=13, column=5, columnspan=2, sticky="e", padx=2)
        self._label("Rate/FreqBand", 14, 0, sticky="w")
        ttk.Combobox(self, state="disabled").grid(row=14, column=1, columnspan=6, sticky="we", padx=2, pady=2)
        if local:
            tk.Label(self, text="Settings for Standard Mavlink\nSettings for Low Latency", bg=BG,
                     font=("DejaVu Sans", 8), justify="left").grid(row=13, column=2, columnspan=3, sticky="w")

        bar = tk.Frame(self, bg=BG)
        bar.grid(row=17, column=2, columnspan=5, sticky="e", pady=2)
        grey_button(bar, "Load from File...", self.load_file, width=14).pack(side="left", padx=2)
        grey_button(bar, "Save to File...", self.save_file, width=12).pack(side="left", padx=2)
        grey_button(bar, "Set PPM Fail Safe", self.app.no_ppm, width=14).pack(side="left", padx=2)
        self.set_enabled(False)

    def _label(self, text, row, col, sticky="w", span=1):
        lab = tk.Label(self, text=text, bg=BG, font=FONT)
        lab.grid(row=row, column=col, columnspan=span, sticky=sticky, padx=6, pady=2)
        self.labels.append(lab)
        return lab

    def _field(self, label, aliases, kind, choices, row, col):
        self._label(label, row, col, sticky="w")
        if kind == "check":
            var = tk.IntVar()
            w = tk.Checkbutton(self, variable=var, bg=BG, activebackground=BG)
            w.grid(row=row, column=col + 1, sticky="w")
        else:
            var = tk.StringVar()
            if kind == "ro":
                w = ttk.Entry(self, textvariable=var, state="readonly", width=10)
            elif kind == "mav":
                w = ttk.Combobox(self, textvariable=var, values=list(MAVLINK.values()), width=10)
            else:
                w = ttk.Combobox(self, textvariable=var, values=choices, width=10)
            w.grid(row=row, column=col + 1, sticky="we", padx=2)
        self.fields[label] = {"aliases": aliases, "kind": kind, "var": var, "w": w, "reg": None}

    # ----- state -----
    def set_enabled(self, on):
        """Connected panels have black labels; every control stays greyed until a Load fills it."""
        for lab in self.labels:
            lab.configure(fg="black" if on else DIM)
        for f in self.fields.values():
            f["w"].configure(state="disabled")
            f["reg"] = None
        if not on:
            self.params = {}

    def clear(self):
        self.version.set("")
        self.rssi.set("")
        self.set_enabled(True)
        for f in self.fields.values():
            f["var"].set(0 if f["kind"] == "check" else "")

    def show(self, params):
        self.params = params
        by_name = {p["name"]: reg for reg, p in params.items()}
        for f in self.fields.values():
            f["reg"] = next((by_name[a] for a in f["aliases"] if a in by_name), None)
            if f["reg"] is None:
                f["w"].configure(state="disabled")
                continue
            f["var"].set(self._to_display(f["kind"], params[f["reg"]]["value"]))
            f["w"].configure(state="readonly" if f["kind"] in ("ro", "mav") else "normal")

    @staticmethod
    def _to_display(kind, value):
        if kind == "check":
            return value
        return MAVLINK.get(value, str(value)) if kind == "mav" else str(value)

    def set_field(self, label, value):
        f = self.fields[label]
        f["var"].set(self._to_display(f["kind"], value))

    def get_field(self, label):
        f = self.fields[label]
        v = f["var"].get()
        if f["kind"] == "mav":
            return {s: k for k, s in MAVLINK.items()}[v]
        return int(v)

    def changes(self):
        """{register: new value} for editable fields that differ from the loaded values."""
        out = {}
        for label, f in self.fields.items():
            if f["reg"] is None or f["kind"] == "ro":
                continue
            try:
                new = self.get_field(label)
            except (ValueError, KeyError):
                continue
            if new != self.params[f["reg"]]["value"]:
                out[f["reg"]] = new
        return out

    # ----- files -----
    def save_file(self):
        if not self.params:
            self.app.status.set("Nothing to save - load settings first")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Radio settings", "*.json")])
        if path:
            with open(path, "w") as fh:
                json.dump(self.params, fh, indent=2)
            self.app.status.set(f"Saved {len(self.params)} parameters to {path}")

    def load_file(self):
        if not self.params:
            self.app.status.set("Load settings from the radio first")
            return
        path = filedialog.askopenfilename(filetypes=[("Radio settings", "*.json")])
        if not path:
            return
        with open(path) as fh:
            saved = json.load(fh)
        by_name = {p["name"]: p["value"] for p in saved.values()}
        for label, f in self.fields.items():
            for a in f["aliases"]:
                if f["reg"] is not None and f["kind"] != "ro" and a in by_name:
                    self.set_field(label, by_name[a])
        self.app.status.set("Loaded from file - press Save Settings to write it to the radio")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RFD900 Tools - Linux")
        self.configure(bg=BG)
        self.geometry("1260x800")
        self.minsize(1180, 760)
        self.jobs = queue.Queue()
        self.lock = threading.Lock()
        self.radio = None
        self.in_cmd = False
        self.remote_ok = False
        self.connected = False
        self._style()
        self._menu()
        self._comport()
        self._settings_area()
        self._bottom()
        self._set_buttons(False)
        self.after(100, self._pump)

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TCombobox", fieldbackground="white", background="#e6e6e6")
        s.configure("green.Horizontal.TProgressbar", background="#06b025", troughcolor="#e6e6e6")

    def _menu(self):
        bar = tk.Menu(self)
        bar.add_command(label="Settings", command=lambda: self.focus_set())
        bar.add_command(label="Terminal", command=self.open_terminal)
        bar.add_command(label="RSSI", command=self.open_rssi)
        self.configure(menu=bar)

    @staticmethod
    def _ports():
        return sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))

    def _comport(self):
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=12, pady=(10, 4))
        box = tk.LabelFrame(top, text="ComPort", bg=BG, font=FONT)
        box.pack(side="left")
        tk.Label(box, text="Port", bg=BG, font=FONT).grid(row=0, column=0, padx=6, pady=4, sticky="w")
        tk.Label(box, text="Baud", bg=BG, font=FONT).grid(row=1, column=0, padx=6, pady=4, sticky="w")
        self.port = tk.StringVar(value=(self._ports() or ["/dev/ttyUSB0"])[0])
        self.baud = tk.StringVar(value="57600")
        self.port_box = ttk.Combobox(box, textvariable=self.port, values=self._ports(), width=18,
                                     postcommand=lambda: self.port_box.configure(values=self._ports()))
        self.port_box.grid(row=0, column=1, padx=4, pady=4)
        ttk.Combobox(box, textvariable=self.baud, values=["9600", "19200", "38400", "57600", "115200"],
                     width=18).grid(row=1, column=1, padx=4, pady=4)
        self.connect_btn = grey_button(top, "Connect", self.on_connect, width=22, height=4)
        self.connect_btn.pack(side="left", padx=20)

    def _settings_area(self):
        outer = tk.LabelFrame(self, text="Settings", bg=BG, font=FONT)
        outer.pack(fill="both", expand=True, padx=12, pady=4)
        buttons = tk.Frame(outer, bg=BG)
        buttons.pack(fill="x", pady=8)
        left = tk.Frame(buttons, bg=BG)
        left.pack(side="left", expand=True)
        self.load_btn = grey_button(left, "Load\nSettings", self.load_settings, width=9, height=2)
        self.load_btn.pack(side="left", padx=4)
        self.save_btn = grey_button(left, "Save\nSettings", self.save_settings, width=9, height=2)
        self.save_btn.pack(side="left", padx=4)
        right = tk.Frame(buttons, bg=BG)
        right.pack(side="left", expand=True)
        self.reset_btn = grey_button(right, "Reset to\nDefaults", self.reset_defaults, width=9, height=2)
        self.reset_btn.pack(side="left", padx=4)
        grey_button(right, "Upload Firmware", self.no_firmware, width=14, height=2).pack(side="left", padx=4)
        leds = tk.Label(right, text="Status Leds", bg=BG, fg="#0000ee", font=("DejaVu Sans", 9, "underline"),
                        cursor="hand2")
        leds.pack(side="left", padx=40)
        leds.bind("<Button-1>", lambda e: messagebox.showinfo("Status Leds", "Not supported in this tool."))

        panels = tk.Frame(outer, bg=BG)
        panels.pack(fill="both", expand=True, padx=4, pady=2)
        self.local = Panel(panels, "Local", self, True)
        self.remote = Panel(panels, "Remote", self, False)
        self.local.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.remote.pack(side="left", fill="both", expand=True)

    def _bottom(self):
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=12)
        self.status = tk.StringVar(value="")
        tk.Label(row, textvariable=self.status, bg=BG, font=FONT).pack(side="left")
        self.copy_btn = grey_button(row, "Copy required to\nremote", self.copy_to_remote, width=16, height=2)
        self.copy_btn.place(relx=0.46, rely=0.0)
        tk.Frame(row, bg=BG, height=40).pack()
        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100,
                                        style="green.Horizontal.TProgressbar")
        self.progress.pack(fill="x", padx=12, pady=(0, 12), ipady=14)

    def _set_buttons(self, on):
        for b in (self.load_btn, self.save_btn, self.reset_btn, self.copy_btn):
            b.configure(state="normal" if on else "disabled")

    # ----- threading helpers -----
    def _pump(self):
        try:
            while True:
                self.jobs.get_nowait()()
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def ui(self, fn):
        self.jobs.put(fn)

    def run(self, fn):
        if self.lock.locked():
            return

        def worker():
            with self.lock:
                try:
                    fn()
                except SystemExit as e:
                    self.say(str(e.code), 0)
                except Exception as e:
                    self.say(f"Error: {e}", 0)

        threading.Thread(target=worker, daemon=True).start()

    def say(self, text, pct=None):
        def f():
            self.status.set(text)
            if pct is not None:
                self.progress.configure(value=pct)
        self.ui(f)

    def ensure_cmd(self):
        if not self.in_cmd:
            self.say("Entering command mode", 10)
            self.radio.enter_command_mode()
            self.in_cmd = True
        self.radio.prefix = "AT"

    # ----- actions -----
    def on_connect(self):
        if self.connected:
            def off():
                if self.radio:
                    try:
                        self.radio.prefix = "AT"
                        self.radio.close()
                    except Exception:
                        pass
                self.radio, self.in_cmd, self.connected = None, False, False
                self.ui(lambda: (self.connect_btn.configure(text="Connect"), self.local.set_enabled(False),
                                 self.remote.set_enabled(False), self._set_buttons(False)))
                self.say("Disconnected", 0)
            self.run(off)
            return

        def job():
            self.radio = Radio(self.port.get(), int(self.baud.get()))
            self.in_cmd = False
            self.ensure_cmd()
            self.connected = True
            self.ui(lambda: (self.connect_btn.configure(text="Disconnect"), self.local.set_enabled(True),
                             self.remote.set_enabled(True), self._set_buttons(True)))
            self.say("Connected - press Load Settings", 0)
        self.run(job)

    def _read_side(self, panel, remote):
        r = self.radio
        r.prefix = "RT" if remote else "AT"
        ver = r.at("I").strip().splitlines()
        params = r.params()
        rssi = "\n".join(l for l in r.at("I7", wait=0.5).strip().splitlines()
                         if not l.upper().startswith(("ATI", "RTI")))
        self.ui(lambda: (panel.version.set(ver[-1] if ver else ""), panel.show(params), panel.rssi.set(rssi)))

    def load_settings(self):
        def job():
            self.ensure_cmd()
            self.ui(lambda: (self.local.clear(), self.remote.clear()))
            self.say("Reading local radio", 40)
            self._read_side(self.local, False)
            self.say("Reading remote radio", 70)
            try:
                self._read_side(self.remote, True)
                self.remote_ok = True
                self.say("Done", 100)
            except SystemExit:
                self.remote_ok = False
                self.say("Done (no remote radio responded)", 100)
            finally:
                self.radio.prefix = "AT"
        self.run(job)

    def _apply(self, remote, changes):
        r = self.radio
        r.prefix = "RT" if remote else "AT"
        for reg, val in changes.items():
            r.set(reg, val)
        if changes:
            r.at("&W")

    def save_settings(self):
        loc = self.local.changes()
        rem = self.remote.changes() if self.remote_ok else {}
        if not loc and not rem:
            self.status.set("Nothing to save")
            return

        def job():
            self.ensure_cmd()
            # remote first so the link survives local changes
            if rem:
                self.say("Writing remote radio", 40)
                self._apply(True, rem)
            if loc:
                self.say("Writing local radio", 70)
                self._apply(False, loc)
            if rem:
                self.radio.prefix = "RT"
                self.radio.at("Z")
            self.radio.prefix = "AT"
            self.radio.at("Z")
            self.in_cmd = False
            self.say("Done - radios rebooted, press Load Settings", 100)
        self.run(job)

    def reset_defaults(self):
        if not messagebox.askyesno("Reset", "Reset the local radio to factory defaults?"):
            return

        def job():
            self.ensure_cmd()
            self.radio.at("&F")
            self.radio.at("&W")
            self.radio.at("Z")
            self.in_cmd = False
            self.ui(lambda: self.local.clear())
            self.say("Reset to defaults - press Load Settings", 100)
        self.run(job)

    def copy_to_remote(self):
        if not self.remote.params:
            self.status.set("Load settings from a remote radio first")
            return
        for label in COPY_TO_REMOTE:
            try:
                self.remote.set_field(label, self.local.get_field(label))
            except (ValueError, KeyError):
                pass
        self.status.set("Copied - press Save Settings")

    def no_firmware(self):
        messagebox.showinfo("Firmware", "Firmware upload isn't supported in this tool.\n"
                            "Use the Windows RFD900 Tools for firmware.")

    def no_ppm(self):
        messagebox.showinfo("PPM Fail Safe", "Not supported in this tool.")

    # ----- menu windows -----
    def open_terminal(self):
        if not self.connected:
            self.status.set("Connect first")
            return
        win = tk.Toplevel(self)
        win.title("Terminal")
        out = tk.Text(win, width=80, height=24, bg="black", fg="#9f9", font=("DejaVu Sans Mono", 10))
        out.pack(fill="both", expand=True)
        entry = tk.Entry(win, font=("DejaVu Sans Mono", 10))
        entry.pack(fill="x")
        entry.focus_set()

        def send(_e=None):
            text = entry.get().strip()
            entry.delete(0, "end")
            if not text:
                return

            def job():
                self.ensure_cmd()
                reply = self.radio.cmd(text, wait=0.7)
                self.ui(lambda: (out.insert("end", f"> {text}\n{reply}\n"), out.see("end")))
            self.run(job)

        entry.bind("<Return>", send)

    def open_rssi(self):
        if not self.connected:
            self.status.set("Connect first")
            return
        win = tk.Toplevel(self)
        win.title("RSSI")
        var = tk.StringVar()
        tk.Label(win, textvariable=var, font=("DejaVu Sans Mono", 10), justify="left", anchor="nw",
                 width=70, height=5).pack(padx=10, pady=10)
        alive = [True]
        win.protocol("WM_DELETE_WINDOW", lambda: (alive.__setitem__(0, False), win.destroy()))

        def tick():
            if not alive[0]:
                return
            if not self.lock.locked():
                def job():
                    self.ensure_cmd()
                    text = "\n".join(l for l in self.radio.at("I7", wait=0.5).splitlines() if l.strip()
                                     and not l.upper().startswith("ATI"))
                    self.ui(lambda: var.set(text))
                self.run(job)
            win.after(1500, tick)
        tick()


if __name__ == "__main__":
    App().mainloop()
