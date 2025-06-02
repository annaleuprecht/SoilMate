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
│SoilMate/
├── GUI_run.py # Main entry point
├── station_config_page.py # Station configuration GUI
├── manual_control_page.py # Manual device control
├── test_set_up_page.py # Test stage definition
├── test_view_page.py # Real-time data display
├── data_view_page.py # Live raw readings
│
├── device_controllers/ # STDDPC, Load Frame, SerialPad drivers
├── calibration_wizard.py # Calibration manager
└── icons/ # App icons


## ✨ Coming Soon
- Exportable test reports (CSV, Excel)
- `.exe` release for non-technical users
- Built-in calibration assistant
- Full test result visualization
