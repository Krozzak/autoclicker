# Grid Auto-Clicker

A powerful, configurable grid-based auto-clicker with a modern GUI. Perfect for automating repetitive clicking tasks on grid layouts.

![Version](https://img.shields.io/badge/version-2.0.0-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![License](https://img.shields.io/badge/license-MIT-orange)

## Features

- **Modern UI** with Dark/Light theme toggle
- **Grid-based clicking** with configurable rows, columns, and spacing
- **Calibration system** - Use F9 hotkey to capture screen positions
- **Timing presets** - Fast, Normal, Conservative modes
- **Economy tracking** - Track costs, rewards, and profit per cycle
- **Live dashboard** - Real-time stats including clicks/min, cycles/min, ETA
- **Auto stop/pause** - Based on cycle count or time limits
- **Input validation** - Visual feedback for invalid settings
- **Standalone executable** - No Python installation required

## Screenshots

### Dark Theme

The application features a sleek dark theme by default, with card-based layouts and intuitive controls.

### Light Theme

Toggle to light theme with a single click for better visibility in bright environments.

## Installation

### Option 1: Standalone Executable (Recommended)

1. Download `GridAutoClicker_V2.exe` from the [Releases](../../releases) page
2. Run the executable - no installation required!

### Option 2: Run from Source

```bash
# Clone the repository
git clone https://github.com/Krozzak/autoclicker.git
cd autoclicker

# Install dependencies
pip install pyautogui pynput

# Run the application
cd v2
python autoclicker_grid_V2.py
```

## Usage

### Quick Start

1. Launch the application
2. Configure your grid in the **Grid** tab:
   - Set origin position (top-left corner)
   - Set step size (distance between positions)
   - Set rows and columns
3. Adjust timing in the **Timing** tab or use a preset
4. Click **Start** and position your target window during the 3-second countdown

### Calibration (F9)

1. In the Grid tab, click "Arm (0,0)"
2. Move your mouse to the center of the first position in your target
3. Press **F9** to capture
4. Repeat for positions (0,1) and (1,0) to auto-calculate spacing

### Hotkeys

| Key | Action |
|-----|--------|
| **ESC** | Stop immediately |
| **F8** | Pause/Resume toggle |
| **F9** | Capture calibration point |

### Economy Tracking

Track your in-game economy by setting:

- **Cost per cycle**: Resources spent per cycle
- **Reward per cycle**: Resources earned per cycle
- **Coin goal**: Target profit to reach

The dashboard will show real-time profit calculations and estimate cycles needed to reach your goal.

## Project Structure

```
autoclicker/
├── v2/                          # Current version
│   ├── autoclicker_grid_V2.py   # Main application
│   ├── AutoClicker_Grid_V2.spec # PyInstaller config
│   └── dist/
│       └── GridAutoClicker_V2.exe
├── v1/                          # Legacy version
│   └── ...
├── autoclicker_state.json       # Settings file
└── README.md
```

## Building from Source

```bash
cd v2
pip install pyinstaller
pyinstaller AutoClicker_Grid_V2.spec
```

The executable will be created in `v2/dist/`.

## Configuration

Settings are automatically saved to `autoclicker_state.json` and persist between sessions. The file includes:

- Grid configuration (origin, step, size)
- Timing settings
- Counter/economy settings
- Theme preference

## Requirements

- Windows 10/11
- Python 3.8+ (if running from source)
- Dependencies: `pyautogui`, `pynput`

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This tool is intended for legitimate automation purposes such as:

- Game farming/grinding (where permitted by game ToS)
- Software testing
- Repetitive task automation

Please use responsibly and in accordance with any applicable terms of service.
