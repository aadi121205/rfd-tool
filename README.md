# rfd-tool

Linux tools for reading and writing settings on **SiK / RFD900X2** telemetry radios — an open replacement for the Windows-only RFD900 Tools.

- `rfdtool.py` — command-line tool (info, dump, set, restore)
- `rfdgui.py` — Tkinter GUI that mimics the RFD900 Tools layout, with local/remote radio panels

## Requirements

- Python 3
- [pyserial](https://pypi.org/project/pyserial/): `pip install pyserial`
- Tkinter for the GUI (`sudo apt install python3-tk`)
- Serial port access (`sudo usermod -aG dialout $USER`, then log out and in)

## CLI usage

Defaults to `/dev/ttyUSB0` at 57600 baud; override with `--port` and `--baud`.

```sh
./rfdtool.py info                        # radio version / board info
./rfdtool.py dump -o radio.json          # print and save all S-registers
./rfdtool.py set S3=25 S4=20             # change registers, save, reboot
./rfdtool.py set S3=25 --no-save         # change without saving to flash
./rfdtool.py restore radio.json          # write a saved dump back
./rfdtool.py dump --remote               # talk to the remote radio (RT commands)
```

## GUI

```sh
./rfdgui.py
```

Pick the serial port, load the local and remote radio settings, edit them, and write them back. Settings the radio doesn't report stay greyed out.

## Notes

- The tool enters command mode with `+++` (needs ~1s of silence on the line), so make sure nothing else (e.g. a ground station) is using the port.
- `S0` (format) is read-only and is skipped on restore.
- Changing air speed, net ID, etc. on only one side will break the link — update both radios.
