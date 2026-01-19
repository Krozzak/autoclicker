# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Grid Auto-Clicker is a configurable automation tool for repetitive clicking tasks on a grid layout. Features a modern Tkinter GUI with dark/light themes, real-time dashboard, and economy tracking.

## Project Structure

```
auto_clicker/
├── v2/                          # Current version (recommended)
│   ├── autoclicker_grid_V2.py   # Main application
│   ├── AutoClicker_Grid_V2.spec # PyInstaller spec
│   ├── autoclicker_grid_icon2.ico
│   └── dist/
│       └── GridAutoClicker_V2.exe  # Standalone executable
├── v1/                          # Legacy version
│   ├── autoclicker_grid_V1.py   # Original GUI (French labels)
│   ├── autoclicker_grid_UI.py   # Earlier UI iteration
│   ├── autoclicker_grid.py      # CLI-only version
│   ├── calibrate_grid.py        # Calibration helper
│   └── AutoClicker_Grid.spec
├── autoclicker_state.json       # Shared state file
└── CLAUDE.md
```

## Running the Application

```bash
# Install dependencies
pip install pyautogui pynput

# Run V2 (recommended)
cd v2
python autoclicker_grid_V2.py

# Or use the standalone executable
./v2/dist/GridAutoClicker_V2.exe

# Build V2 executable
cd v2
pyinstaller AutoClicker_Grid_V2.spec
```

## V2 Architecture

### Theme System
- `THEMES` dict defines light/dark color palettes
- `ThemeManager` class handles theme switching and ttk style configuration
- Theme preference persists in state file

### State Management
- Dataclasses: `GridConfig`, `TimingConfig`, `CounterConfig` wrapped in `AppState`
- Persists to `autoclicker_state.json`
- V1 to V2 migration handled automatically via `V1_FIELD_MIGRATION` map

### Threading Model
- Main thread: Tkinter event loop
- Worker thread: Runs `run_cycles()` for clicking automation
- Global `threading.Event` objects: `stop_event`, `pause_event`
- `runtime_lock` protects shared counters
- UI updates from worker use `self.after(0, callback)`

### UI Components
- `StatusBar`: State indicator (READY/RUNNING/PAUSED/STOPPED), progress, timer
- `CountdownOverlay`: 3-second countdown before start
- `InputValidator`: Field validation with visual feedback
- Live dashboard with time stats, click stats, economy tracking

### Terminology (V2)
- "clicks" = individual click actions
- "cycles" = complete cycle count (every N clicks per position)
- "positions" = grid locations

### Economy Tracking
- `cost_per_cycle`: Cost in coins per cycle
- `reward_per_cycle`: Reward in coins per cycle
- `coin_goal`: Target coins to earn
- Dashboard shows: spent, earned, net profit, cycles to goal

### Timing Presets
- Fast: Aggressive timing (cooldown=5s)
- Normal: Balanced (cooldown=8s)
- Conservative: Safe (cooldown=12s)

## Hotkeys (Global)

- **ESC**: Stop immediately
- **F8**: Toggle pause/resume
- **F9**: Capture calibration point (arm point in GUI first)

## GUI Calibration

1. In Grid tab, click "Arm (0,0)"
2. Position mouse over target position in your application
3. Press F9 to capture
4. Repeat for (0,1) and (1,0) to auto-calculate step_x/step_y
