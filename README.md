# SoilMate v2025

**SoilMate** is a Python-based graphical user interface (GUI) for automated triaxial testing. The goal of the project is to provide a clean and user-friendly interface for configuring tests, controlling devices, and logging data.

## 🚧 Current Features

- 🔧 **Station Configuration** – Auto-detect and connect to:
  - LF50 Load Frame
  - STDDPC v2 Pressure Controllers (x2)
  - 8-Channel SerialPad
- 🎛 **Manual Control Page** – Manually send commands for:
  - Axial displacement
  - Pressure or volume control
- 📈 **Data View Page** – Live readouts from transducers on serial pad
- 🧪 **Test Setup Page** – Define test stages with custom pressure/displacement inputs
- 📊 **Test View Page** – Real-time graphing during tests, customizable y-axis variables

## 🧰 Hardware Compatibility

- GDS Instruments LF50 Load Frame
- GDS STDDPC v2 Pressure Controllers (cell and back)
- GDS SerialPad (8-channel analog)

## 📦 Getting Started

> **Note:** Python 3.9+ is recommended.

1. Clone this repository:
    ```bash
    git clone https://github.com/yourusername/SoilMate.git
    cd SoilMate
    ```

2. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

3. Run the GUI:
    ```bash
    python GUI_run.py
    ```

## 📁 Project Structure
SoilMate/
├── GUI_run.py                   # Main application entry point
├── calibration_wizard.py        # Manages calibration loading and parsing
├── station_config_page.py       # GUI for detecting and connecting devices
├── manual_control_page.py       # Manual control interface for pressure and axial commands
├── test_set_up_page.py          # UI for configuring test stages (saturation, B test, etc.)
├── test_view_page.py            # Real-time graphing and test monitoring
├── data_view_page.py            # Live display of transducer data from SerialPad
│
├── device_controllers/          # Device-specific driver logic
│   ├── sttdpc_controller.py     # STDDPC v2 pressure controller driver
│   ├── loadframe.py             # LF50 USB initialization and communication
│   ├── lf50_movement.py         # Axial displacement command builder
│   └── serial_pad_reader.py     # 8-channel SerialPad ADC reader
│
└── icons/                       # Sidebar and button icons

## ✨ Coming Soon
- Exportable test reports (CSV, Excel)
- `.exe` release for non-technical users
- Built-in calibration assistant
- Full test result visualization
