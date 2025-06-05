# SoilMate

**SoilMate** is an open-source Python-based GUI for automated triaxial testing of soil specimens. It provides a modular and customizable interface to control pressure controllers, load frames, and SerialPad data acquisition systems.

## Features

- Manual control of pressure and displacement
- Live data acquisition and graphing
- Automated testing workflows (Saturation, B-test, Consolidation, Shear)
- Modular device interface system (PyUSB + Serial)

## Supported Devices

- GDS STDDPC v2 Pressure Controllers (via USB)
- GDS LF50 Load Frame (via USB)
- GDS SerialPad 8-channel reader (via RS232)

## Legal Disclaimer

This project was developed through independent reverse engineering for the purpose of enabling interoperability with GDS hardware owned by the author.

- No original GDSLab source code, binaries, or proprietary assets are included or used in this repository.
- All communication protocols were reverse engineered using publicly available tools (e.g., USB capture, serial logs).
- This project does not clone or redistribute any GDS proprietary features or software.
- This project is not affiliated with or endorsed by GDS Instruments.

Reverse engineering was conducted in accordance with fair use (Canada/US) and fair dealing (UK/EU) principles for educational and non-commercial research purposes.

## Installation

Coming soon — will include steps to:
- Install required Python packages
- Set up USB drivers (via Zadig)
- Run the GUI application

## License

MIT License.
