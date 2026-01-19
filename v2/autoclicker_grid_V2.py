"""
autoclicker_grid_V2.py
Grid Auto-Clicker - A configurable automation tool

Features:
- Dark/Light theme toggle
- Input validation with visual feedback
- Status bar with state indicators
- Timing presets (Fast/Normal/Conservative)
- Progress tracking for target completion
- Live dashboard with economy tracking
- Enhanced grid and timing visualizations

Hotkeys:
  - ESC : Immediate stop
  - F8  : Pause/Resume toggle
  - F9  : Calibration capture

Dependencies:
  pip install pyautogui pynput
"""

import json
import time
import threading
import random
import statistics
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, Tuple, Optional, Callable, List
import pyautogui
from pynput import keyboard

import tkinter as tk
from tkinter import ttk

# =============================================================================
# Version & App Info
# =============================================================================

VERSION = "2.0.0"
APP_NAME = "Grid Auto-Clicker"
BUILD_DATE = "2026-01"

# =============================================================================
# Theme Configuration
# =============================================================================

THEMES = {
    "light": {
        "bg": "#ffffff",
        "fg": "#1f2937",
        "bg_secondary": "#f3f4f6",
        "bg_tertiary": "#e5e7eb",
        "accent": "#2563eb",
        "accent_hover": "#1d4ed8",
        "accent_light": "#dbeafe",
        "border": "#d1d5db",
        "border_light": "#e5e7eb",
        "error": "#dc2626",
        "error_bg": "#fef2f2",
        "error_light": "#fca5a5",
        "success": "#16a34a",
        "success_bg": "#f0fdf4",
        "success_light": "#86efac",
        "warning": "#d97706",
        "warning_bg": "#fffbeb",
        "canvas_bg": "#ffffff",
        "card_bg": "#f9fafb",
        "card_border": "#e5e7eb",
        "text_muted": "#6b7280",
        "text_secondary": "#374151",
        "input_bg": "#ffffff",
        "input_border": "#d1d5db",
        "input_focus": "#2563eb",
        "progress_bg": "#e5e7eb",
        "progress_fill": "#2563eb",
    },
    "dark": {
        "bg": "#111827",
        "fg": "#f9fafb",
        "bg_secondary": "#1f2937",
        "bg_tertiary": "#374151",
        "accent": "#3b82f6",
        "accent_hover": "#60a5fa",
        "accent_light": "#1e3a5f",
        "border": "#374151",
        "border_light": "#4b5563",
        "error": "#f87171",
        "error_bg": "#450a0a",
        "error_light": "#991b1b",
        "success": "#4ade80",
        "success_bg": "#052e16",
        "success_light": "#166534",
        "warning": "#fbbf24",
        "warning_bg": "#451a03",
        "canvas_bg": "#1f2937",
        "card_bg": "#1f2937",
        "card_border": "#374151",
        "text_muted": "#9ca3af",
        "text_secondary": "#d1d5db",
        "input_bg": "#374151",
        "input_border": "#4b5563",
        "input_focus": "#3b82f6",
        "progress_bg": "#374151",
        "progress_fill": "#3b82f6",
    }
}

STATUS_COLORS = {
    "READY": {"light": "#16a34a", "dark": "#4ade80"},
    "RUNNING": {"light": "#2563eb", "dark": "#3b82f6"},
    "PAUSED": {"light": "#d97706", "dark": "#fbbf24"},
    "STOPPED": {"light": "#6b7280", "dark": "#9ca3af"},
}

# =============================================================================
# Timing Presets
# =============================================================================

PRESETS = {
    "Fast": {
        "description": "Aggressive timing for maximum speed",
        "timing": {
            "cooldown_seconds": 5.0,
            "click_delay": 0.10,
            "between_positions_delay": 0.08,
            "click_delay_jitter": 0.03,
            "between_positions_jitter": 0.05,
        }
    },
    "Normal": {
        "description": "Balanced timing (recommended)",
        "timing": {
            "cooldown_seconds": 8.0,
            "click_delay": 0.16,
            "between_positions_delay": 0.15,
            "click_delay_jitter": 0.06,
            "between_positions_jitter": 0.10,
        }
    },
    "Conservative": {
        "description": "Safe timing with longer delays",
        "timing": {
            "cooldown_seconds": 12.0,
            "click_delay": 0.25,
            "between_positions_delay": 0.25,
            "click_delay_jitter": 0.08,
            "between_positions_jitter": 0.15,
        }
    }
}

# =============================================================================
# Persistence
# =============================================================================

STATE_FILE = Path("autoclicker_state.json")

# =============================================================================
# Config Dataclasses
# =============================================================================

@dataclass
class GridConfig:
    origin_x: int = 854
    origin_y: int = 400
    step_x: int = 84
    step_y: int = 84
    rows: int = 5
    cols: int = 4
    offset_dx: int = 0
    offset_dy: int = 0
    random_offset_px: int = 20


@dataclass
class TimingConfig:
    cooldown_seconds: float = 8.0
    always_second_click: bool = True
    click_delay: float = 0.16
    between_positions_delay: float = 0.20
    click_delay_jitter: float = 0.06
    between_positions_jitter: float = 0.15


@dataclass
class CounterConfig:
    # Cycle tracking (renamed from shovels)
    start_cycles_done: int = 0
    target_cycles: Optional[int] = None
    pause_at_cycles: Optional[int] = None

    # Time limits
    stop_after_minutes: Optional[float] = None
    pause_after_minutes: Optional[float] = None

    # Click/cycle ratio
    clicks_per_cycle: int = 3
    start_full_grown: bool = True

    # Stats
    stats_window: int = 20

    # Economy tracking
    cost_per_cycle: int = 0
    reward_per_cycle: int = 0
    coin_goal: Optional[int] = None


@dataclass
class AppState:
    grid: GridConfig = field(default_factory=GridConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    counters: CounterConfig = field(default_factory=CounterConfig)

    # Session persistence
    last_session_cycles_added: int = 0
    last_session_clicks: int = 0
    last_run_timestamp: float = 0.0

    # Theme preference
    theme: str = "dark"

    # State version for migration
    version: str = "2.0"


def default_state() -> AppState:
    return AppState()


# V1 to V2 field migration map
V1_FIELD_MIGRATION = {
    "counters": {
        "start_shovels_done": "start_cycles_done",
        "target_shovels": "target_cycles",
        "pause_at_shovels": "pause_at_cycles",
        "harvests_per_shovel": "clicks_per_cycle",
    },
    "timing": {
        "between_tiles_delay": "between_positions_delay",
        "between_tiles_jitter": "between_positions_jitter",
    },
    "root": {
        "last_session_shovels_added": "last_session_cycles_added",
        "last_session_harvests": "last_session_clicks",
    }
}


def load_state() -> AppState:
    """Load state with V1->V2 migration support."""
    if not STATE_FILE.exists():
        return default_state()

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        st = default_state()

        # Check if this is a V1 state file (no version field)
        is_v1 = "version" not in data

        if is_v1:
            # Apply V1 -> V2 migrations
            for group, mappings in V1_FIELD_MIGRATION.items():
                if group == "root":
                    for old_key, new_key in mappings.items():
                        if old_key in data:
                            data[new_key] = data[old_key]
                elif group in data and isinstance(data[group], dict):
                    for old_key, new_key in mappings.items():
                        if old_key in data[group]:
                            data[group][new_key] = data[group][old_key]

        # Load grid config
        if "grid" in data and isinstance(data["grid"], dict):
            for k, v in data["grid"].items():
                if hasattr(st.grid, k):
                    setattr(st.grid, k, v)

        # Load timing config
        if "timing" in data and isinstance(data["timing"], dict):
            for k, v in data["timing"].items():
                if hasattr(st.timing, k):
                    setattr(st.timing, k, v)

        # Load counter config
        if "counters" in data and isinstance(data["counters"], dict):
            for k, v in data["counters"].items():
                if hasattr(st.counters, k):
                    setattr(st.counters, k, v)

        # Load root-level fields
        for k in ("last_session_cycles_added", "last_session_clicks",
                  "last_run_timestamp", "theme", "version"):
            if k in data:
                setattr(st, k, data[k])

        return st
    except Exception as e:
        print(f"Error loading state: {e}")
        return default_state()


def save_state(st: AppState) -> None:
    """Save state to JSON file."""
    payload = {
        "version": st.version,
        "theme": st.theme,
        "grid": asdict(st.grid),
        "timing": asdict(st.timing),
        "counters": asdict(st.counters),
        "last_session_cycles_added": st.last_session_cycles_added,
        "last_session_clicks": st.last_session_clicks,
        "last_run_timestamp": st.last_run_timestamp,
    }
    STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# =============================================================================
# Core Runtime
# =============================================================================

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.0

stop_event = threading.Event()
pause_event = threading.Event()

cycle_times: List[float] = []
runtime_lock = threading.Lock()

# Runtime counters (session)
session_clicks = 0
session_cycles_added = 0
session_pause_time = 0.0
session_active_time = 0.0

# Per-position click counts
per_position_clicks: Dict[Tuple[int, int], int] = {}
run_start_time: Optional[float] = None
current_position: Optional[Tuple[int, int]] = None

# UI callbacks
log_fn: Optional[Callable[[str], None]] = None
calib_fn: Optional[Callable[[str, int, int], None]] = None
calib_armed_point: Optional[str] = None


def log(msg: str):
    """Log to UI if available; else print."""
    if log_fn:
        log_fn(msg)
    else:
        print(msg)


def jittered(base: float, jitter: float) -> float:
    """Uniform jitter around base; never below 0."""
    if jitter <= 0:
        return max(0.0, base)
    return max(0.0, base + random.uniform(-jitter, jitter))


def random_offset(px: int) -> Tuple[int, int]:
    """Random pixel offset in [-px, +px]."""
    if px <= 0:
        return 0, 0
    return random.randint(-px, px), random.randint(-px, px)


def wait_if_paused(step: float = 0.1) -> float:
    """Block while paused. Returns time spent paused."""
    pause_start = time.monotonic()
    while pause_event.is_set() and not stop_event.is_set():
        time.sleep(step)
    return time.monotonic() - pause_start


def sleep_interruptible(seconds: float, step: float = 0.05) -> float:
    """Sleep in small slices. Returns total pause time during this sleep."""
    global session_pause_time
    total_pause = 0.0
    end = time.monotonic() + seconds

    while time.monotonic() < end:
        if stop_event.is_set():
            return total_pause
        if pause_event.is_set():
            pause_duration = wait_if_paused(step=max(step, 0.1))
            total_pause += pause_duration
            with runtime_lock:
                session_pause_time += pause_duration
            end += pause_duration
            continue
        time.sleep(step)

    return total_pause


def on_key_press(key):
    """Global hotkeys."""
    global calib_armed_point

    if key == keyboard.Key.esc:
        log("[STOP] ESC pressed. Stopping...")
        stop_event.set()

    elif key == keyboard.Key.f8:
        if pause_event.is_set():
            pause_event.clear()
            log("[RESUME] Resumed (F8)")
        else:
            pause_event.set()
            log("[PAUSE] Paused (F8)")

    elif key == keyboard.Key.f9:
        if calib_armed_point is None:
            log("[CALIB] F9 ignored: no point armed. Arm a point in Grid tab first.")
            return

        x, y = pyautogui.position()
        point = calib_armed_point
        calib_armed_point = None

        log(f"[CALIB] Captured {point} via F9: x={x}, y={y}")

        if calib_fn:
            calib_fn(point, int(x), int(y))


def start_hotkey_listener():
    """Start background keyboard listener."""
    listener = keyboard.Listener(on_press=on_key_press)
    listener.daemon = True
    listener.start()
    return listener


def click_position(center_x: int, center_y: int, grid: GridConfig, timing: TimingConfig) -> None:
    """Click a position with optional second click."""
    if stop_event.is_set():
        return

    wait_if_paused()

    dx, dy = random_offset(int(grid.random_offset_px))
    x = center_x + dx
    y = center_y + dy

    # Click #1
    pyautogui.click(x, y)
    if stop_event.is_set():
        return

    # Click #2 (optional)
    if timing.always_second_click:
        interval = jittered(timing.click_delay, timing.click_delay_jitter)
        sleep_interruptible(interval)
        if stop_event.is_set():
            return
        wait_if_paused()
        pyautogui.click(x, y)

    # Between positions delay
    between = jittered(timing.between_positions_delay, timing.between_positions_jitter)
    sleep_interruptible(between)


def should_count_cycle(position_click_count: int, counter_cfg: CounterConfig) -> bool:
    """Determine if this click counts as a cycle completion."""
    n = max(1, int(counter_cfg.clicks_per_cycle))
    return ((position_click_count - 1) % n) == 0


def print_stats(counter_cfg: CounterConfig, timing: TimingConfig, base_cycles_done: int):
    """Print cycle stats + counters."""
    if not cycle_times:
        return

    window = cycle_times[-counter_cfg.stats_window:]
    avg = statistics.mean(window)
    mn = min(window)
    mx = max(window)

    with runtime_lock:
        total_cycles_done = base_cycles_done + session_cycles_added
        c = session_clicks
        s = session_cycles_added

    log(f"[STATS] cycles={len(cycle_times)} | avg({len(window)})={avg:.2f}s | min={mn:.2f}s | max={mx:.2f}s")
    log(f"[COUNT] clicks_session={c} | cycles_added={s} | cycles_total={total_cycles_done}")

    if avg > timing.cooldown_seconds:
        log(f"[WARN] Average > {timing.cooldown_seconds:.1f}s - consider reducing delays")
    else:
        log("[INFO] Average < cooldown - running efficiently")


def maybe_pause_or_stop(counter_cfg: CounterConfig, base_cycles_done: int):
    """Apply pause/stop rules based on counters + time."""
    if run_start_time is None:
        return

    elapsed_minutes = (time.monotonic() - run_start_time) / 60.0

    with runtime_lock:
        total_cycles_done = base_cycles_done + session_cycles_added

    # STOP by target cycles
    if counter_cfg.target_cycles is not None and total_cycles_done >= counter_cfg.target_cycles:
        log(f"[STOP AUTO] Target cycles reached: {total_cycles_done}/{counter_cfg.target_cycles}")
        stop_event.set()
        return

    # STOP by time
    if counter_cfg.stop_after_minutes is not None and elapsed_minutes >= counter_cfg.stop_after_minutes:
        log(f"[STOP AUTO] Time limit reached: {elapsed_minutes:.1f} / {counter_cfg.stop_after_minutes} min")
        stop_event.set()
        return

    # PAUSE by cycles
    if counter_cfg.pause_at_cycles is not None and total_cycles_done >= counter_cfg.pause_at_cycles:
        if not pause_event.is_set():
            pause_event.set()
            log(f"[PAUSE AUTO] Cycle limit reached: {total_cycles_done}/{counter_cfg.pause_at_cycles} (F8 to resume)")
        return

    # PAUSE by time
    if counter_cfg.pause_after_minutes is not None and elapsed_minutes >= counter_cfg.pause_after_minutes:
        if not pause_event.is_set():
            pause_event.set()
            log(f"[PAUSE AUTO] Time limit reached: {elapsed_minutes:.1f} / {counter_cfg.pause_after_minutes} min (F8 to resume)")
        return


def run_cycles(state: AppState):
    """Main clicking loop."""
    global per_position_clicks, session_clicks, session_cycles_added
    global run_start_time, cycle_times, session_pause_time, session_active_time
    global current_position

    grid = state.grid
    timing = state.timing
    counter_cfg = state.counters

    base_cycles_done = int(counter_cfg.start_cycles_done)

    origin_x = int(grid.origin_x + grid.offset_dx)
    origin_y = int(grid.origin_y + grid.offset_dy)
    rows = max(1, int(grid.rows))
    cols = max(1, int(grid.cols))

    # Per position readiness times
    ready_at = {(r, c): 0.0 for r in range(rows) for c in range(cols)}

    # Per position click count
    per_position_clicks = {(r, c): 0 for r in range(rows) for c in range(cols)}

    cycle_times = []

    with runtime_lock:
        session_clicks = 0
        session_cycles_added = 0
        session_pause_time = 0.0
        session_active_time = 0.0

    run_start_time = time.monotonic()

    cycle = 0
    log("=== START === (ESC stop / F8 pause)")

    while not stop_event.is_set():
        wait_if_paused()

        cycle += 1
        log(f"=== Cycle {cycle} ===")

        t0 = time.monotonic()
        next_start = t0 + float(timing.cooldown_seconds)

        for r in range(rows):
            for c in range(cols):
                if stop_event.is_set():
                    break

                wait_if_paused()

                current_position = (r, c)

                # Wait until this position is ready
                now = time.monotonic()
                wait = ready_at[(r, c)] - now
                if wait > 0:
                    sleep_interruptible(wait)
                    if stop_event.is_set():
                        break

                # Compute position center
                x = origin_x + c * int(grid.step_x)
                y = origin_y + r * int(grid.step_y)

                # Click position
                click_position(x, y, grid, timing)

                # Count click
                with runtime_lock:
                    session_clicks += 1

                # Update per position click count
                per_position_clicks[(r, c)] += 1
                pos_clicks = per_position_clicks[(r, c)]

                # Cycle count rule
                if should_count_cycle(pos_clicks, counter_cfg):
                    with runtime_lock:
                        session_cycles_added += 1
                        total_cycles_done = base_cycles_done + session_cycles_added

                    # Calculate profit for this cycle
                    net_profit = counter_cfg.reward_per_cycle - counter_cfg.cost_per_cycle
                    profit_msg = f" (+{net_profit} coins)" if net_profit != 0 else ""
                    log(f"[CYCLE] Position({r},{c}) click#{pos_clicks} -> +1 cycle | total={total_cycles_done}{profit_msg}")

                # Apply auto pause/stop rules
                maybe_pause_or_stop(counter_cfg, base_cycles_done)
                if stop_event.is_set():
                    break

                # Position ready again after cooldown
                ready_at[(r, c)] = time.monotonic() + float(timing.cooldown_seconds)

            if stop_event.is_set():
                break

        elapsed = time.monotonic() - t0
        cycle_times.append(elapsed)

        with runtime_lock:
            session_active_time = time.monotonic() - run_start_time - session_pause_time

        log(f"Cycle completed in {elapsed:.2f}s")
        print_stats(counter_cfg, timing, base_cycles_done)

        if stop_event.is_set():
            break

        # Global cycle deadline wait
        remaining = next_start - time.monotonic()
        if remaining > 0:
            log(f"Waiting for cooldown: {remaining:.2f}s")
            sleep_interruptible(remaining)
        else:
            log(f"Behind schedule by {-remaining:.2f}s, continuing immediately")

    current_position = None
    log("=== STOPPED ===")


# =============================================================================
# Theme Manager
# =============================================================================

class ThemeManager:
    """Manages theme switching for ttk and tk widgets."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.current_theme = "dark"
        self.style = ttk.Style()
        self._callbacks: List[Callable[[str], None]] = []
        self._setup_base_style()

    def _setup_base_style(self):
        """Set up base ttk style."""
        self.style.theme_use("clam")

    def register_callback(self, callback: Callable[[str], None]):
        """Register a callback to be called when theme changes."""
        self._callbacks.append(callback)

    def get_colors(self) -> dict:
        """Get current theme colors."""
        return THEMES[self.current_theme]

    def apply_theme(self, theme_name: str):
        """Switch to the specified theme."""
        if theme_name not in THEMES:
            return

        self.current_theme = theme_name
        colors = THEMES[theme_name]

        # Configure root window
        self.root.configure(bg=colors["bg"])

        # Configure ttk styles
        self.style.configure(".",
            background=colors["bg"],
            foreground=colors["fg"],
            fieldbackground=colors["input_bg"],
            troughcolor=colors["progress_bg"]
        )

        # TFrame
        self.style.configure("TFrame", background=colors["bg"])
        self.style.configure("Card.TFrame",
            background=colors["card_bg"],
            relief="solid",
            borderwidth=1
        )

        # TLabel
        self.style.configure("TLabel",
            background=colors["bg"],
            foreground=colors["fg"]
        )
        self.style.configure("Card.TLabel", background=colors["card_bg"])
        self.style.configure("Muted.TLabel", foreground=colors["text_muted"])
        self.style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"))
        self.style.configure("Title.TLabel", font=("Segoe UI", 14, "bold"))
        self.style.configure("Big.TLabel", font=("Segoe UI", 24, "bold"))

        # TButton
        self.style.configure("TButton",
            background=colors["bg_secondary"],
            foreground=colors["fg"],
            padding=(12, 6)
        )
        self.style.map("TButton",
            background=[("active", colors["bg_tertiary"]), ("pressed", colors["bg_tertiary"])]
        )

        self.style.configure("Accent.TButton",
            background=colors["accent"],
            foreground="#ffffff"
        )
        self.style.map("Accent.TButton",
            background=[("active", colors["accent_hover"]), ("pressed", colors["accent_hover"])]
        )

        # TEntry
        self.style.configure("TEntry",
            fieldbackground=colors["input_bg"],
            foreground=colors["fg"],
            insertcolor=colors["fg"]
        )
        self.style.configure("Error.TEntry",
            fieldbackground=colors["error_bg"]
        )

        # TCombobox
        self.style.configure("TCombobox",
            fieldbackground=colors["input_bg"],
            background=colors["input_bg"],
            foreground=colors["fg"]
        )

        # TNotebook
        self.style.configure("TNotebook",
            background=colors["bg"],
            borderwidth=0
        )
        self.style.configure("TNotebook.Tab",
            background=colors["bg_secondary"],
            foreground=colors["fg"],
            padding=(16, 8)
        )
        self.style.map("TNotebook.Tab",
            background=[("selected", colors["bg"])],
            foreground=[("selected", colors["accent"])]
        )

        # TProgressbar
        self.style.configure("TProgressbar",
            background=colors["progress_fill"],
            troughcolor=colors["progress_bg"],
            borderwidth=0,
            thickness=20
        )

        # TSeparator
        self.style.configure("TSeparator", background=colors["border"])

        # TCheckbutton
        self.style.configure("TCheckbutton",
            background=colors["bg"],
            foreground=colors["fg"]
        )

        # Notify callbacks
        for callback in self._callbacks:
            callback(theme_name)

    def toggle_theme(self) -> str:
        """Toggle between light and dark themes."""
        new_theme = "dark" if self.current_theme == "light" else "light"
        self.apply_theme(new_theme)
        return new_theme


# =============================================================================
# Input Validator
# =============================================================================

class InputValidator:
    """Validates input fields and provides visual feedback."""

    def __init__(self, theme_manager: ThemeManager):
        self.theme_manager = theme_manager
        self.validation_state: Dict[str, bool] = {}

    @staticmethod
    def validate_int(value: str, min_val: Optional[int] = None, max_val: Optional[int] = None,
                     required: bool = False) -> Tuple[bool, str]:
        """Validate integer input."""
        value = value.strip()
        if value == "":
            if required:
                return False, "Required"
            return True, ""
        try:
            v = int(float(value))
            if min_val is not None and v < min_val:
                return False, f"Min: {min_val}"
            if max_val is not None and v > max_val:
                return False, f"Max: {max_val}"
            return True, ""
        except ValueError:
            return False, "Invalid number"

    @staticmethod
    def validate_float(value: str, min_val: Optional[float] = None, max_val: Optional[float] = None,
                       required: bool = False) -> Tuple[bool, str]:
        """Validate float input."""
        value = value.strip()
        if value == "":
            if required:
                return False, "Required"
            return True, ""
        try:
            v = float(value)
            if min_val is not None and v < min_val:
                return False, f"Min: {min_val}"
            if max_val is not None and v > max_val:
                return False, f"Max: {max_val}"
            return True, ""
        except ValueError:
            return False, "Invalid number"

    def is_all_valid(self) -> bool:
        """Check if all tracked fields are valid."""
        return all(self.validation_state.values())


# =============================================================================
# Status Bar Widget
# =============================================================================

class StatusBar(ttk.Frame):
    """Application status bar with state indicator and progress."""

    STATES = ["READY", "RUNNING", "PAUSED", "STOPPED"]

    def __init__(self, parent, theme_manager: ThemeManager):
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.current_state = "READY"

        self._build_ui()
        theme_manager.register_callback(self._on_theme_change)

    def _build_ui(self):
        colors = self.theme_manager.get_colors()

        # State indicator
        state_frame = ttk.Frame(self)
        state_frame.pack(side="left", padx=(10, 20))

        self.state_dot = tk.Canvas(state_frame, width=12, height=12,
                                   highlightthickness=0, bg=colors["bg"])
        self.state_dot.pack(side="left", padx=(0, 8))

        self.state_label = ttk.Label(state_frame, text="READY",
                                     font=("Segoe UI", 10, "bold"))
        self.state_label.pack(side="left")

        # Separator
        ttk.Separator(self, orient="vertical").pack(side="left", fill="y", padx=10, pady=4)

        # Progress section
        progress_frame = ttk.Frame(self)
        progress_frame.pack(side="left", fill="x", expand=True)

        self.progress_label = ttk.Label(progress_frame,
                                        text="Clicks: 0 | Cycles: 0 / --")
        self.progress_label.pack(side="left", padx=(0, 15))

        self.progress_bar = ttk.Progressbar(progress_frame,
                                            length=200, mode="determinate")
        self.progress_bar.pack(side="left", padx=(0, 10))
        self.progress_bar.pack_forget()  # Hidden by default

        # Timer display
        self.timer_label = ttk.Label(self, text="00:00:00",
                                     font=("Segoe UI Mono", 10))
        self.timer_label.pack(side="right", padx=10)

        self._draw_state_dot()

    def _on_theme_change(self, theme_name: str):
        colors = THEMES[theme_name]
        self.state_dot.configure(bg=colors["bg"])
        self._draw_state_dot()

    def set_state(self, state: str):
        """Update the status bar state."""
        if state not in self.STATES:
            return
        self.current_state = state
        self.state_label.configure(text=state)
        self._draw_state_dot()

    def _draw_state_dot(self):
        """Draw the colored state indicator dot."""
        self.state_dot.delete("all")
        theme = self.theme_manager.current_theme
        color = STATUS_COLORS.get(self.current_state, {}).get(theme, "#6b7280")
        self.state_dot.create_oval(2, 2, 10, 10, fill=color, outline="")

    def update_progress(self, clicks: int, cycles: int, target: Optional[int],
                        elapsed_seconds: float):
        """Update progress display."""
        target_str = str(target) if target else "--"
        self.progress_label.configure(
            text=f"Clicks: {clicks:,} | Cycles: {cycles} / {target_str}"
        )

        if target and target > 0:
            self.progress_bar.pack(side="left", padx=(0, 10))
            progress_pct = min(100, (cycles / target) * 100)
            self.progress_bar["value"] = progress_pct
        else:
            self.progress_bar.pack_forget()

        # Format elapsed time
        hours, remainder = divmod(int(elapsed_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        self.timer_label.configure(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")


# =============================================================================
# Countdown Overlay
# =============================================================================

class CountdownOverlay(tk.Toplevel):
    """Semi-transparent countdown overlay before start."""

    def __init__(self, parent, seconds: int, on_complete: Callable, on_cancel: Callable):
        super().__init__(parent)
        self.seconds = seconds
        self.on_complete = on_complete
        self.on_cancel = on_cancel
        self._cancelled = False

        # Configure as overlay
        self.overrideredirect(True)
        self.attributes("-topmost", True)

        # Center on screen
        width, height = 320, 220
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

        # Dark background
        self.configure(bg="#1f2937")

        # Title
        tk.Label(
            self, text="Starting...",
            font=("Segoe UI", 14),
            fg="#9ca3af", bg="#1f2937"
        ).pack(pady=(25, 10))

        # Countdown number
        self.countdown_label = tk.Label(
            self, text=str(seconds),
            font=("Segoe UI", 72, "bold"),
            fg="#3b82f6", bg="#1f2937"
        )
        self.countdown_label.pack(expand=True)

        # Instruction
        tk.Label(
            self, text="Position your target window",
            font=("Segoe UI", 11),
            fg="#6b7280", bg="#1f2937"
        ).pack(pady=(0, 15))

        # Cancel button
        cancel_btn = tk.Button(
            self, text="Cancel (ESC)",
            command=self._cancel,
            bg="#374151", fg="#f9fafb",
            activebackground="#4b5563", activeforeground="#f9fafb",
            relief="flat", padx=25, pady=8,
            font=("Segoe UI", 10)
        )
        cancel_btn.pack(pady=(0, 25))

        # Bind ESC key
        self.bind("<Escape>", lambda e: self._cancel())
        self.focus_set()

        # Start countdown
        self._tick()

    def _tick(self):
        """Update countdown."""
        if self._cancelled:
            return

        if self.seconds <= 0:
            self.destroy()
            self.on_complete()
            return

        self.countdown_label.configure(text=str(self.seconds))
        self.seconds -= 1
        self.after(1000, self._tick)

    def _cancel(self):
        """Cancel countdown."""
        self._cancelled = True
        self.on_cancel()
        self.destroy()


# =============================================================================
# Main Application
# =============================================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{VERSION}")
        self.geometry("1100x850")
        self.minsize(900, 700)

        # Try to set icon
        try:
            self.iconbitmap("autoclicker_grid_icon2.ico")
        except:
            pass

        # Initialize theme manager
        self.theme_manager = ThemeManager(self)

        # Initialize validator
        self.validator = InputValidator(self.theme_manager)

        # Load saved state
        self.state_obj = load_state()

        # Worker thread
        self.worker_thread: Optional[threading.Thread] = None

        # UI variables
        self.vars: Dict[str, tk.StringVar] = {}
        self._preview_job = None
        self._dashboard_job = None

        # Calibration storage
        self._calib_points: Dict[str, Optional[Tuple[int, int]]] = {
            "p00": None, "p01": None, "p10": None
        }

        # Build UI
        self._build_ui()

        # Apply saved theme
        self.theme_manager.apply_theme(self.state_obj.theme)
        self._update_theme_button()

        # Attach logger
        global log_fn
        log_fn = self.append_log

        # Attach calibration callback
        global calib_fn
        def _calib_dispatch(point: str, x: int, y: int) -> None:
            self.after(0, lambda: self.apply_calibration_point(point, x, y))
        calib_fn = _calib_dispatch

        # Start hotkey listener
        start_hotkey_listener()

        # Register theme callback for canvas updates
        self.theme_manager.register_callback(self._on_theme_change)

        # Start refresh loops
        self.after(200, self._refresh_loop)

        # Auto update previews
        self._install_traces()
        self.update_previews()

        # Window close handler
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Initial log
        self.append_log(f"Welcome to {APP_NAME} v{VERSION}")
        self.append_log("Hotkeys: ESC=Stop | F8=Pause/Resume | F9=Calibration")

    # -------------------------------------------------------------------------
    # UI Helpers
    # -------------------------------------------------------------------------

    def _var(self, name: str, default) -> tk.StringVar:
        v = tk.StringVar(value=str(default) if default is not None else "")
        self.vars[name] = v
        return v

    def _create_card(self, parent, title: str) -> Tuple[tk.Frame, tk.Frame]:
        """Create a card-style section with title."""
        colors = self.theme_manager.get_colors()

        # Outer frame with border effect
        outer = tk.Frame(parent, bg=colors["card_border"], padx=1, pady=1)

        # Inner card
        card = tk.Frame(outer, bg=colors["card_bg"], padx=15, pady=12)
        card.pack(fill="both", expand=True)

        # Title
        title_label = tk.Label(card, text=title, font=("Segoe UI", 11, "bold"),
                               bg=colors["card_bg"], fg=colors["fg"])
        title_label.pack(anchor="w", pady=(0, 10))

        # Content frame
        content = tk.Frame(card, bg=colors["card_bg"])
        content.pack(fill="both", expand=True)

        # Store references for theme updates
        outer._inner_card = card  # type: ignore[attr-defined]
        outer._title_label = title_label  # type: ignore[attr-defined]
        outer._content = content  # type: ignore[attr-defined]

        return outer, content

    def _create_labeled_entry(self, parent, label: str, var: tk.StringVar,
                               width: int = 12, row: int = 0,
                               validator_type: str = "int",
                               min_val=None, max_val=None,
                               required: bool = False) -> ttk.Entry:
        """Create a labeled entry with validation."""
        colors = self.theme_manager.get_colors()
        bg = parent.cget("bg") if isinstance(parent, tk.Frame) else colors["card_bg"]

        # Label
        lbl = tk.Label(parent, text=label, font=("Segoe UI", 10),
                       bg=bg, fg=colors["fg"])
        lbl.grid(row=row, column=0, sticky="w", pady=4)

        # Entry
        entry = ttk.Entry(parent, textvariable=var, width=width)
        entry.grid(row=row, column=1, sticky="w", padx=(10, 5), pady=4)

        # Validation indicator
        indicator = tk.Label(parent, text="", font=("Segoe UI", 10),
                            bg=bg, width=2)
        indicator.grid(row=row, column=2, sticky="w", pady=4)

        # Store references
        entry._label = lbl  # type: ignore[attr-defined]
        entry._indicator = indicator  # type: ignore[attr-defined]

        # Validation callback
        def validate(*args):
            value = var.get()
            if validator_type == "int":
                is_valid, msg = self.validator.validate_int(value, min_val, max_val, required)
            else:
                is_valid, msg = self.validator.validate_float(value, min_val, max_val, required)

            self.validator.validation_state[label] = is_valid

            if is_valid:
                entry.configure(style="TEntry")
                indicator.configure(text="", fg=colors["success"])
            else:
                entry.configure(style="Error.TEntry")
                indicator.configure(text="!", fg=colors["error"])

        var.trace_add("write", validate)
        validate()  # Initial validation

        return entry

    def append_log(self, msg: str):
        """Thread-safe log append."""
        def _do():
            ts = time.strftime("%H:%M:%S")
            self.log_text.insert("end", f"[{ts}] {msg}\n")
            self.log_text.see("end")
            # Limit log size
            lines = int(self.log_text.index("end-1c").split(".")[0])
            if lines > 500:
                self.log_text.delete("1.0", "100.0")
        self.after(0, _do)

    def _read_int(self, name: str, default: int = 0) -> int:
        s = self.vars.get(name, tk.StringVar()).get().strip()
        if s == "":
            return default
        try:
            return int(float(s))
        except ValueError:
            return default

    def _read_float(self, name: str, default: float = 0.0) -> float:
        s = self.vars.get(name, tk.StringVar()).get().strip()
        if s == "":
            return default
        try:
            return float(s)
        except ValueError:
            return default

    def _read_optional_int(self, name: str) -> Optional[int]:
        s = self.vars.get(name, tk.StringVar()).get().strip()
        if s == "":
            return None
        try:
            return int(float(s))
        except ValueError:
            return None

    def _read_optional_float(self, name: str) -> Optional[float]:
        s = self.vars.get(name, tk.StringVar()).get().strip()
        if s == "":
            return None
        try:
            return float(s)
        except ValueError:
            return None

    # -------------------------------------------------------------------------
    # Build UI
    # -------------------------------------------------------------------------

    def _build_ui(self):
        # Top bar
        self._build_top_bar()

        # Status bar
        self.status_bar = StatusBar(self, self.theme_manager)
        self.status_bar.pack(fill="x", padx=10, pady=(0, 5))

        # Separator
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10)

        # Notebook
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=10)

        # Tabs
        self.tab_grid = ttk.Frame(self.nb)
        self.tab_timing = ttk.Frame(self.nb)
        self.tab_counters = ttk.Frame(self.nb)
        self.tab_activity = ttk.Frame(self.nb)

        self.nb.add(self.tab_grid, text="  Grid  ")
        self.nb.add(self.tab_timing, text="  Timing  ")
        self.nb.add(self.tab_counters, text="  Counters  ")
        self.nb.add(self.tab_activity, text="  Activity  ")

        # Build tabs
        self._build_grid_tab()
        self._build_timing_tab()
        self._build_counters_tab()
        self._build_activity_tab()

    def _build_top_bar(self):
        """Build the top control bar."""
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=10)

        # Left: Action buttons
        btn_frame = ttk.Frame(top)
        btn_frame.pack(side="left")

        self.btn_start = ttk.Button(btn_frame, text="Start",
                                    command=self.start, style="Accent.TButton")
        self.btn_start.pack(side="left", padx=(0, 8))

        ttk.Button(btn_frame, text="Pause", command=self.pause).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Resume", command=self.resume).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Stop", command=self.stop).pack(side="left", padx=4)

        ttk.Separator(btn_frame, orient="vertical").pack(side="left", fill="y", padx=12)

        ttk.Button(btn_frame, text="Load", command=self.load_from_disk).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Save", command=self.save_to_disk).pack(side="left", padx=4)

        # Right: Theme toggle + About
        right_frame = ttk.Frame(top)
        right_frame.pack(side="right")

        self.theme_btn = ttk.Button(right_frame, text="Light Mode",
                                    command=self._toggle_theme, width=12)
        self.theme_btn.pack(side="left", padx=4)

        ttk.Button(right_frame, text="About", command=self._show_about).pack(side="left", padx=(4, 0))

    def _build_grid_tab(self):
        """Build the Grid configuration tab."""
        colors = self.theme_manager.get_colors()
        g = self.state_obj.grid

        # Main container with two columns
        main = ttk.Frame(self.tab_grid)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Left column: Configuration
        left = ttk.Frame(main)
        left.pack(side="left", fill="y", padx=(0, 10))

        # Grid Settings Card
        card_outer, card = self._create_card(left, "Grid Settings")
        card_outer.pack(fill="x", pady=(0, 10))

        self._create_labeled_entry(card, "Origin X", self._var("origin_x", g.origin_x),
                                   row=0, min_val=0)
        self._create_labeled_entry(card, "Origin Y", self._var("origin_y", g.origin_y),
                                   row=1, min_val=0)
        self._create_labeled_entry(card, "Step X", self._var("step_x", g.step_x),
                                   row=2, min_val=1)
        self._create_labeled_entry(card, "Step Y", self._var("step_y", g.step_y),
                                   row=3, min_val=1)
        self._create_labeled_entry(card, "Rows", self._var("rows", g.rows),
                                   row=4, min_val=1, max_val=20)
        self._create_labeled_entry(card, "Columns", self._var("cols", g.cols),
                                   row=5, min_val=1, max_val=20)

        # Offset Card
        card_outer2, card2 = self._create_card(left, "Offsets")
        card_outer2.pack(fill="x", pady=(0, 10))

        self._create_labeled_entry(card2, "Offset DX", self._var("offset_dx", g.offset_dx),
                                   row=0)
        self._create_labeled_entry(card2, "Offset DY", self._var("offset_dy", g.offset_dy),
                                   row=1)
        self._create_labeled_entry(card2, "Click Spread (px)", self._var("random_offset_px", g.random_offset_px),
                                   row=2, min_val=0, max_val=100)

        # Calibration Card
        card_outer3, card3 = self._create_card(left, "Calibration (F9)")
        card_outer3.pack(fill="x")

        calib_info = tk.Label(card3, text="1. Click 'Arm', 2. Position mouse, 3. Press F9",
                             font=("Segoe UI", 9), bg=colors["card_bg"], fg=colors["text_muted"])
        calib_info.pack(anchor="w", pady=(0, 8))

        btn_frame = ttk.Frame(card3)
        btn_frame.pack(anchor="w")

        ttk.Button(btn_frame, text="Arm (0,0)",
                   command=lambda: self._arm_calibration("p00")).pack(side="left", padx=(0, 5))
        ttk.Button(btn_frame, text="Arm (0,1)",
                   command=lambda: self._arm_calibration("p01")).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Arm (1,0)",
                   command=lambda: self._arm_calibration("p10")).pack(side="left", padx=5)

        self.calib_status = tk.Label(card3, text="Points: (0,0)=--  (0,1)=--  (1,0)=--",
                                     font=("Segoe UI", 9), bg=colors["card_bg"], fg=colors["text_muted"])
        self.calib_status.pack(anchor="w", pady=(8, 0))

        ttk.Button(card3, text="Reset Calibration",
                   command=self._reset_calibration).pack(anchor="w", pady=(8, 0))

        # Right column: Preview
        right = ttk.Frame(main)
        right.pack(side="left", fill="both", expand=True)

        # Preview Card
        preview_outer, preview_card = self._create_card(right, "Grid Preview")
        preview_outer.pack(fill="both", expand=True)

        self.grid_canvas = tk.Canvas(preview_card, width=500, height=400,
                                     bg=colors["canvas_bg"], highlightthickness=1,
                                     highlightbackground=colors["border"])
        self.grid_canvas.pack(fill="both", expand=True)

        preview_info = tk.Label(preview_card,
                               text="Blue squares show click spread area (±random_offset_px). Numbers show click order.",
                               font=("Segoe UI", 9), bg=colors["card_bg"], fg=colors["text_muted"])
        preview_info.pack(anchor="w", pady=(8, 0))

    def _build_timing_tab(self):
        """Build the Timing configuration tab."""
        colors = self.theme_manager.get_colors()
        t = self.state_obj.timing

        main = ttk.Frame(self.tab_timing)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Left column
        left = ttk.Frame(main)
        left.pack(side="left", fill="y", padx=(0, 10))

        # Presets Card
        preset_outer, preset_card = self._create_card(left, "Presets")
        preset_outer.pack(fill="x", pady=(0, 10))

        preset_frame = ttk.Frame(preset_card)
        preset_frame.pack(fill="x")

        self.preset_var = tk.StringVar(value="Normal")
        preset_combo = ttk.Combobox(preset_frame, textvariable=self.preset_var,
                                    values=list(PRESETS.keys()), state="readonly", width=15)
        preset_combo.pack(side="left", padx=(0, 10))

        ttk.Button(preset_frame, text="Apply", command=self._apply_preset).pack(side="left")

        self.preset_desc = tk.Label(preset_card, text=PRESETS["Normal"]["description"],
                                    font=("Segoe UI", 9), bg=colors["card_bg"], fg=colors["text_muted"])
        self.preset_desc.pack(anchor="w", pady=(8, 0))

        preset_combo.bind("<<ComboboxSelected>>", self._update_preset_desc)

        # Timing Settings Card
        timing_outer, timing_card = self._create_card(left, "Timing Settings")
        timing_outer.pack(fill="x", pady=(0, 10))

        self._create_labeled_entry(timing_card, "Cooldown (s)",
                                   self._var("cooldown_seconds", t.cooldown_seconds),
                                   row=0, validator_type="float", min_val=0.1)
        self._create_labeled_entry(timing_card, "Click Delay (s)",
                                   self._var("click_delay", t.click_delay),
                                   row=1, validator_type="float", min_val=0)
        self._create_labeled_entry(timing_card, "Between Positions (s)",
                                   self._var("between_positions_delay", t.between_positions_delay),
                                   row=2, validator_type="float", min_val=0)

        # Jitter Card
        jitter_outer, jitter_card = self._create_card(left, "Jitter (Randomization)")
        jitter_outer.pack(fill="x")

        self._create_labeled_entry(jitter_card, "Click Jitter (s)",
                                   self._var("click_delay_jitter", t.click_delay_jitter),
                                   row=0, validator_type="float", min_val=0)
        self._create_labeled_entry(jitter_card, "Position Jitter (s)",
                                   self._var("between_positions_jitter", t.between_positions_jitter),
                                   row=1, validator_type="float", min_val=0)

        self.always_second_click_var = tk.BooleanVar(value=t.always_second_click)
        chk = ttk.Checkbutton(jitter_card, text="Always perform second click",
                             variable=self.always_second_click_var)
        chk.grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))

        # Right column: Timeline Preview
        right = ttk.Frame(main)
        right.pack(side="left", fill="both", expand=True)

        timeline_outer, timeline_card = self._create_card(right, "Timing Timeline")
        timeline_outer.pack(fill="both", expand=True)

        self.timing_canvas = tk.Canvas(timeline_card, width=550, height=180,
                                       bg=colors["canvas_bg"], highlightthickness=1,
                                       highlightbackground=colors["border"])
        self.timing_canvas.pack(fill="x", pady=(0, 10))

        self.timing_info = tk.Label(timeline_card, text="",
                                    font=("Segoe UI", 10), bg=colors["card_bg"], fg=colors["fg"])
        self.timing_info.pack(anchor="w")

        timing_legend = tk.Label(timeline_card,
                                text="Timeline shows: Click 1 → Delay → Click 2 → Between Positions. Shaded areas = jitter range.",
                                font=("Segoe UI", 9), bg=colors["card_bg"], fg=colors["text_muted"])
        timing_legend.pack(anchor="w", pady=(8, 0))

    def _build_counters_tab(self):
        """Build the Counters configuration tab."""
        colors = self.theme_manager.get_colors()
        c = self.state_obj.counters

        main = ttk.Frame(self.tab_counters)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Left column
        left = ttk.Frame(main)
        left.pack(side="left", fill="y", padx=(0, 10))

        # Cycle Tracking Card
        cycle_outer, cycle_card = self._create_card(left, "Cycle Tracking")
        cycle_outer.pack(fill="x", pady=(0, 10))

        self._create_labeled_entry(cycle_card, "Cycles Completed",
                                   self._var("start_cycles_done", c.start_cycles_done),
                                   row=0, min_val=0)
        self._create_labeled_entry(cycle_card, "Target Cycles",
                                   self._var("target_cycles", c.target_cycles),
                                   row=1, min_val=1)
        self._create_labeled_entry(cycle_card, "Clicks per Cycle",
                                   self._var("clicks_per_cycle", c.clicks_per_cycle),
                                   row=2, min_val=1)

        self.start_full_grown_var = tk.BooleanVar(value=c.start_full_grown)
        chk = ttk.Checkbutton(cycle_card, text="Start with full cycle (count from click 1)",
                             variable=self.start_full_grown_var)
        chk.grid(row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))

        # Auto Stop/Pause Card
        auto_outer, auto_card = self._create_card(left, "Auto Stop / Pause")
        auto_outer.pack(fill="x", pady=(0, 10))

        self._create_labeled_entry(auto_card, "Pause at Cycles",
                                   self._var("pause_at_cycles", c.pause_at_cycles),
                                   row=0, min_val=1)
        self._create_labeled_entry(auto_card, "Stop after (min)",
                                   self._var("stop_after_minutes", c.stop_after_minutes),
                                   row=1, validator_type="float", min_val=0.1)
        self._create_labeled_entry(auto_card, "Pause after (min)",
                                   self._var("pause_after_minutes", c.pause_after_minutes),
                                   row=2, validator_type="float", min_val=0.1)

        # Economy Card
        econ_outer, econ_card = self._create_card(left, "Economy Tracking")
        econ_outer.pack(fill="x")

        self._create_labeled_entry(econ_card, "Cost per Cycle",
                                   self._var("cost_per_cycle", c.cost_per_cycle),
                                   row=0, min_val=0)
        self._create_labeled_entry(econ_card, "Reward per Cycle",
                                   self._var("reward_per_cycle", c.reward_per_cycle),
                                   row=1, min_val=0)
        self._create_labeled_entry(econ_card, "Coin Goal",
                                   self._var("coin_goal", c.coin_goal),
                                   row=2, min_val=1)

        # Calculate net profit display
        net_frame = tk.Frame(econ_card, bg=colors["card_bg"])
        net_frame.grid(row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))

        self.net_profit_label = tk.Label(net_frame, text="Net per cycle: 0 coins",
                                         font=("Segoe UI", 10, "bold"),
                                         bg=colors["card_bg"], fg=colors["success"])
        self.net_profit_label.pack(anchor="w")

        # Right column: Info
        right = ttk.Frame(main)
        right.pack(side="left", fill="both", expand=True)

        info_outer, info_card = self._create_card(right, "How It Works")
        info_outer.pack(fill="x")

        info_text = """Cycle Counting:
• A "cycle" is counted every N clicks on the same position
• With "Start with full cycle" enabled, first click counts
• Example: clicks_per_cycle=3 → cycles at click 1, 4, 7...

Economy Tracking:
• Cost = what you spend per cycle (e.g., tool cost)
• Reward = what you earn per cycle (e.g., harvest value)
• Net profit = Reward - Cost
• Set a Coin Goal to track progress toward earnings target

The dashboard will show real-time economy stats during execution."""

        info_label = tk.Label(info_card, text=info_text, font=("Segoe UI", 10),
                             bg=colors["card_bg"], fg=colors["text_secondary"],
                             justify="left")
        info_label.pack(anchor="w")

    def _build_activity_tab(self):
        """Build the Activity/Dashboard tab."""
        colors = self.theme_manager.get_colors()

        main = ttk.Frame(self.tab_activity)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Dashboard area (top)
        self.dashboard_frame = ttk.Frame(main)
        self.dashboard_frame.pack(fill="x", pady=(0, 10))

        self._build_dashboard()

        # Log area (bottom)
        log_outer, log_card = self._create_card(main, "Activity Log")
        log_outer.pack(fill="both", expand=True)

        # Log text with scrollbar
        log_frame = ttk.Frame(log_card)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(log_frame, height=10, wrap="word",
                               bg=colors["input_bg"], fg=colors["fg"],
                               font=("Consolas", 10),
                               insertbackground=colors["fg"])
        self.log_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _build_dashboard(self):
        """Build the dashboard widgets."""
        colors = self.theme_manager.get_colors()

        # Clear existing
        for widget in self.dashboard_frame.winfo_children():
            widget.destroy()

        # Progress Card
        prog_outer, prog_card = self._create_card(self.dashboard_frame, "Progress")
        prog_outer.pack(fill="x", pady=(0, 10))

        # Progress bar
        self.dash_progress = ttk.Progressbar(prog_card, length=400, mode="determinate",
                                             style="TProgressbar")
        self.dash_progress.pack(fill="x", pady=(0, 5))

        prog_info = ttk.Frame(prog_card)
        prog_info.pack(fill="x")

        self.dash_progress_pct = tk.Label(prog_info, text="0%", font=("Segoe UI", 14, "bold"),
                                          bg=colors["card_bg"], fg=colors["accent"])
        self.dash_progress_pct.pack(side="left")

        self.dash_progress_text = tk.Label(prog_info, text="Cycles: 0 / -- | Remaining: --",
                                           font=("Segoe UI", 10), bg=colors["card_bg"], fg=colors["text_muted"])
        self.dash_progress_text.pack(side="right")

        # Stats row
        stats_frame = ttk.Frame(self.dashboard_frame)
        stats_frame.pack(fill="x", pady=(0, 10))

        # Time Card
        time_outer, time_card = self._create_card(stats_frame, "Time")
        time_outer.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.dash_runtime = self._create_stat_row(time_card, "Runtime:", "00:00:00", 0)
        self.dash_active = self._create_stat_row(time_card, "Active:", "00:00:00", 1)
        self.dash_paused = self._create_stat_row(time_card, "Paused:", "00:00:00", 2)
        self.dash_eta = self._create_stat_row(time_card, "ETA:", "--:--:--", 3)

        # Clicks Card
        clicks_outer, clicks_card = self._create_card(stats_frame, "Clicks")
        clicks_outer.pack(side="left", fill="both", expand=True, padx=5)

        self.dash_clicks = self._create_stat_row(clicks_card, "Total Clicks:", "0", 0)
        self.dash_cycles = self._create_stat_row(clicks_card, "Total Cycles:", "0", 1)
        self.dash_cpm = self._create_stat_row(clicks_card, "Clicks/min:", "0", 2)
        self.dash_cypm = self._create_stat_row(clicks_card, "Cycles/min:", "0", 3)

        # Economy Card
        econ_outer, econ_card = self._create_card(stats_frame, "Economy")
        econ_outer.pack(side="left", fill="both", expand=True, padx=(5, 0))

        self.dash_spent = self._create_stat_row(econ_card, "Spent:", "0", 0)
        self.dash_earned = self._create_stat_row(econ_card, "Earned:", "0", 1)
        self.dash_profit = self._create_stat_row(econ_card, "Net Profit:", "0", 2)
        self.dash_goal_cycles = self._create_stat_row(econ_card, "Cycles to Goal:", "--", 3)

    def _create_stat_row(self, parent, label: str, value: str, row: int) -> tk.Label:
        """Create a stat label row and return the value label."""
        colors = self.theme_manager.get_colors()
        bg = colors["card_bg"]

        lbl = tk.Label(parent, text=label, font=("Segoe UI", 10),
                      bg=bg, fg=colors["text_muted"])
        lbl.grid(row=row, column=0, sticky="w", pady=2)

        val = tk.Label(parent, text=value, font=("Segoe UI", 10, "bold"),
                      bg=bg, fg=colors["fg"])
        val.grid(row=row, column=1, sticky="e", padx=(20, 0), pady=2)

        return val

    # -------------------------------------------------------------------------
    # Preview Updates
    # -------------------------------------------------------------------------

    def _install_traces(self):
        """Install variable traces for auto-updating previews."""
        preview_vars = [
            "origin_x", "origin_y", "step_x", "step_y", "rows", "cols",
            "offset_dx", "offset_dy", "random_offset_px",
            "cooldown_seconds", "click_delay", "between_positions_delay",
            "click_delay_jitter", "between_positions_jitter",
            "cost_per_cycle", "reward_per_cycle"
        ]

        for name in preview_vars:
            if name in self.vars:
                self.vars[name].trace_add("write", lambda *a: self._schedule_preview_update())

        self.always_second_click_var.trace_add("write", lambda *a: self._schedule_preview_update())

    def _schedule_preview_update(self):
        """Debounced preview update."""
        if self._preview_job:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(100, self.update_previews)

    def update_previews(self):
        """Update all preview canvases."""
        self._preview_job = None
        self._update_grid_preview()
        self._update_timing_preview()
        self._update_economy_display()

    def _update_grid_preview(self):
        """Draw the grid preview with click spread zones."""
        cv = self.grid_canvas
        cv.delete("all")

        colors = self.theme_manager.get_colors()

        origin_x = self._read_int("origin_x", 0) + self._read_int("offset_dx", 0)
        origin_y = self._read_int("origin_y", 0) + self._read_int("offset_dy", 0)
        step_x = max(1, self._read_int("step_x", 1))
        step_y = max(1, self._read_int("step_y", 1))
        rows = max(1, self._read_int("rows", 1))
        cols = max(1, self._read_int("cols", 1))
        spread = max(0, self._read_int("random_offset_px", 0))

        w = cv.winfo_width() or 500
        h = cv.winfo_height() or 400
        margin = 40

        # Bounding box
        min_x = origin_x - spread - step_x // 2
        min_y = origin_y - spread - step_y // 2
        max_x = origin_x + (cols - 1) * step_x + spread + step_x // 2
        max_y = origin_y + (rows - 1) * step_y + spread + step_y // 2

        bw = max(1, max_x - min_x)
        bh = max(1, max_y - min_y)

        # Scale to fit
        sx = (w - 2 * margin) / bw
        sy = (h - 2 * margin) / bh
        scale = min(sx, sy)

        def tx(x): return margin + (x - min_x) * scale
        def ty(y): return margin + (y - min_y) * scale

        # Draw click order path
        positions = []
        for r in range(rows):
            for c in range(cols):
                cx = origin_x + c * step_x
                cy = origin_y + r * step_y
                positions.append((tx(cx), ty(cy)))

        # Draw path lines
        if len(positions) > 1:
            for i in range(len(positions) - 1):
                x1, y1 = positions[i]
                x2, y2 = positions[i + 1]
                cv.create_line(x1, y1, x2, y2, fill=colors["border"], width=1, dash=(4, 4))

        # Draw positions
        click_num = 0
        for r in range(rows):
            for c in range(cols):
                cx = origin_x + c * step_x
                cy = origin_y + r * step_y
                click_num += 1

                x = tx(cx)
                y = ty(cy)

                # Spread zone
                if spread > 0:
                    x1 = tx(cx - spread)
                    y1 = ty(cy - spread)
                    x2 = tx(cx + spread)
                    y2 = ty(cy + spread)
                    cv.create_rectangle(x1, y1, x2, y2,
                                       outline=colors["accent"],
                                       fill=colors["accent_light"],
                                       width=1)

                # Center point
                cv.create_oval(x - 5, y - 5, x + 5, y + 5,
                              fill=colors["accent"], outline="")

                # Click number
                cv.create_text(x, y - 15, text=str(click_num),
                              fill=colors["fg"], font=("Segoe UI", 9, "bold"))

                # Position label
                cv.create_text(x, y + 15, text=f"({r},{c})",
                              fill=colors["text_muted"], font=("Segoe UI", 8))

        # Info text
        info = f"Grid: {rows}x{cols} = {rows*cols} positions | Origin: ({origin_x}, {origin_y}) | Step: ({step_x}, {step_y}) | Spread: ±{spread}px"
        cv.create_text(w // 2, h - 15, text=info, fill=colors["text_muted"], font=("Segoe UI", 9))

    def _update_timing_preview(self):
        """Draw the timing timeline visualization."""
        cv = self.timing_canvas
        cv.delete("all")

        colors = self.theme_manager.get_colors()

        cooldown = max(0.0, self._read_float("cooldown_seconds", 0.0))
        click_delay = max(0.0, self._read_float("click_delay", 0.0))
        click_j = max(0.0, self._read_float("click_delay_jitter", 0.0))
        between = max(0.0, self._read_float("between_positions_delay", 0.0))
        between_j = max(0.0, self._read_float("between_positions_jitter", 0.0))

        rows = max(1, self._read_int("rows", 1))
        cols = max(1, self._read_int("cols", 1))
        n_positions = rows * cols

        second_click = self.always_second_click_var.get()

        w = cv.winfo_width() or 550
        h = cv.winfo_height() or 180
        margin = 30
        baseline_y = h // 2

        # Calculate ranges
        cd_min = max(0.0, click_delay - click_j) if second_click else 0.0
        cd_max = (click_delay + click_j) if second_click else 0.0
        bt_min = max(0.0, between - between_j)
        bt_max = between + between_j

        per_pos_min = cd_min + bt_min
        per_pos_max = cd_max + bt_max

        traverse_min = n_positions * per_pos_min
        traverse_max = n_positions * per_pos_max

        cycle_min = max(cooldown, traverse_min)
        cycle_max = max(cooldown, traverse_max)

        # Draw timeline
        total_time = per_pos_max if per_pos_max > 0 else 1.0

        def tx(t): return margin + (w - 2 * margin) * (t / total_time)

        # Background bar
        cv.create_rectangle(margin, baseline_y - 25, w - margin, baseline_y + 25,
                           fill=colors["bg_secondary"], outline=colors["border"])

        # Click 1 marker
        cv.create_line(margin, baseline_y - 30, margin, baseline_y + 30,
                      fill=colors["accent"], width=3)
        cv.create_text(margin, baseline_y - 40, text="Click 1",
                      fill=colors["accent"], font=("Segoe UI", 9, "bold"))

        # Click 2 range (if enabled)
        if second_click and click_delay > 0:
            x1 = tx(cd_min)
            x2 = tx(cd_max)
            cv.create_rectangle(x1, baseline_y - 20, x2, baseline_y + 20,
                               fill=colors["accent_light"], outline=colors["accent"])
            cv.create_line(tx(click_delay), baseline_y - 25, tx(click_delay), baseline_y + 25,
                          fill=colors["accent"], width=2)
            cv.create_text((x1 + x2) / 2, baseline_y - 35, text="Click 2",
                          fill=colors["accent"], font=("Segoe UI", 9, "bold"))

        # Between positions range
        end_min = cd_min + bt_min
        end_max = cd_max + bt_max
        if between > 0:
            x1 = tx(end_min)
            x2 = tx(end_max)
            cv.create_rectangle(x1, baseline_y - 15, x2, baseline_y + 15,
                               fill=colors["success_bg"], outline=colors["success"])
            cv.create_text((x1 + x2) / 2, baseline_y + 35, text="Next Position",
                          fill=colors["success"], font=("Segoe UI", 9))

        # End marker
        cv.create_line(w - margin, baseline_y - 30, w - margin, baseline_y + 30,
                      fill=colors["text_muted"], width=2, dash=(4, 4))

        # Update info label
        self.timing_info.configure(
            text=f"Per position: {per_pos_min:.2f}s - {per_pos_max:.2f}s | "
                 f"Full grid ({n_positions} pos): {traverse_min:.2f}s - {traverse_max:.2f}s | "
                 f"Cycle (cooldown={cooldown:.1f}s): {cycle_min:.2f}s - {cycle_max:.2f}s"
        )

    def _update_economy_display(self):
        """Update the economy net profit display."""
        cost = self._read_int("cost_per_cycle", 0)
        reward = self._read_int("reward_per_cycle", 0)
        net = reward - cost

        colors = self.theme_manager.get_colors()
        color = colors["success"] if net >= 0 else colors["error"]

        self.net_profit_label.configure(
            text=f"Net per cycle: {net:+,} coins",
            fg=color
        )

    # -------------------------------------------------------------------------
    # Theme Handling
    # -------------------------------------------------------------------------

    def _toggle_theme(self):
        """Toggle between light and dark theme."""
        new_theme = self.theme_manager.toggle_theme()
        self.state_obj.theme = new_theme
        self._update_theme_button()

    def _update_theme_button(self):
        """Update theme button text."""
        text = "Light Mode" if self.theme_manager.current_theme == "dark" else "Dark Mode"
        self.theme_btn.configure(text=text)

    def _on_theme_change(self, theme_name: str):
        """Handle theme change - update non-ttk widgets."""
        colors = THEMES[theme_name]

        # Update canvases
        if hasattr(self, "grid_canvas"):
            self.grid_canvas.configure(bg=colors["canvas_bg"],
                                       highlightbackground=colors["border"])
        if hasattr(self, "timing_canvas"):
            self.timing_canvas.configure(bg=colors["canvas_bg"],
                                        highlightbackground=colors["border"])

        # Update log text
        if hasattr(self, "log_text"):
            self.log_text.configure(bg=colors["input_bg"], fg=colors["fg"],
                                   insertbackground=colors["fg"])

        # Rebuild dashboard with new colors
        if hasattr(self, "dashboard_frame"):
            self._build_dashboard()

        # Update previews
        self.update_previews()

    # -------------------------------------------------------------------------
    # Calibration
    # -------------------------------------------------------------------------

    def _arm_calibration(self, point_name: str):
        """Arm a calibration point for F9 capture."""
        global calib_armed_point
        calib_armed_point = point_name
        name = {"p00": "(0,0)", "p01": "(0,1)", "p10": "(1,0)"}.get(point_name, point_name)
        self.append_log(f"[CALIB] Point {name} armed. Go to target, position mouse, press F9.")
        self._update_calib_status(armed=point_name)

    def _reset_calibration(self):
        """Reset calibration points."""
        global calib_armed_point
        calib_armed_point = None
        self._calib_points = {"p00": None, "p01": None, "p10": None}
        self._update_calib_status()
        self.append_log("[CALIB] Calibration reset.")

    def apply_calibration_point(self, point_name: str, x: int, y: int):
        """Apply a captured calibration point."""
        self._calib_points[point_name] = (x, y)

        p00 = self._calib_points.get("p00")
        p01 = self._calib_points.get("p01")
        p10 = self._calib_points.get("p10")

        if p00:
            self.vars["origin_x"].set(str(p00[0]))
            self.vars["origin_y"].set(str(p00[1]))

        if p00 and p01:
            step_x = p01[0] - p00[0]
            self.vars["step_x"].set(str(step_x))

        if p00 and p10:
            step_y = p10[1] - p00[1]
            self.vars["step_y"].set(str(step_y))

        self.append_log(f"[CALIB] Applied {point_name}: ({x}, {y})")
        self._update_calib_status()
        self.update_previews()

    def _update_calib_status(self, armed: Optional[str] = None):
        """Update calibration status display."""
        p00 = self._calib_points.get("p00")
        p01 = self._calib_points.get("p01")
        p10 = self._calib_points.get("p10")

        def fmt(p): return "--" if not p else f"{p[0]},{p[1]}"

        armed_txt = f" | Armed: {armed}" if armed else ""

        colors = self.theme_manager.get_colors()
        self.calib_status.configure(
            text=f"Points: (0,0)={fmt(p00)}  (0,1)={fmt(p01)}  (1,0)={fmt(p10)}{armed_txt}",
            fg=colors["text_muted"]
        )

    # -------------------------------------------------------------------------
    # Presets
    # -------------------------------------------------------------------------

    def _update_preset_desc(self, event=None):
        """Update preset description."""
        preset_name = self.preset_var.get()
        if preset_name in PRESETS:
            colors = self.theme_manager.get_colors()
            self.preset_desc.configure(text=PRESETS[preset_name]["description"],
                                       fg=colors["text_muted"])

    def _apply_preset(self):
        """Apply selected timing preset."""
        preset_name = self.preset_var.get()
        if preset_name not in PRESETS:
            return

        timing = PRESETS[preset_name]["timing"]
        for key, value in timing.items():
            if key in self.vars:
                self.vars[key].set(str(value))

        self.append_log(f"Applied preset: {preset_name}")

    # -------------------------------------------------------------------------
    # State Sync
    # -------------------------------------------------------------------------

    def _sync_state_from_ui(self):
        """Copy UI fields to state object."""
        g = self.state_obj.grid
        g.origin_x = self._read_int("origin_x", g.origin_x)
        g.origin_y = self._read_int("origin_y", g.origin_y)
        g.step_x = self._read_int("step_x", g.step_x)
        g.step_y = self._read_int("step_y", g.step_y)
        g.rows = self._read_int("rows", g.rows)
        g.cols = self._read_int("cols", g.cols)
        g.offset_dx = self._read_int("offset_dx", g.offset_dx)
        g.offset_dy = self._read_int("offset_dy", g.offset_dy)
        g.random_offset_px = self._read_int("random_offset_px", g.random_offset_px)

        t = self.state_obj.timing
        t.cooldown_seconds = self._read_float("cooldown_seconds", t.cooldown_seconds)
        t.click_delay = self._read_float("click_delay", t.click_delay)
        t.between_positions_delay = self._read_float("between_positions_delay", t.between_positions_delay)
        t.click_delay_jitter = self._read_float("click_delay_jitter", t.click_delay_jitter)
        t.between_positions_jitter = self._read_float("between_positions_jitter", t.between_positions_jitter)
        t.always_second_click = self.always_second_click_var.get()

        c = self.state_obj.counters
        c.start_cycles_done = self._read_int("start_cycles_done", c.start_cycles_done)
        c.target_cycles = self._read_optional_int("target_cycles")
        c.pause_at_cycles = self._read_optional_int("pause_at_cycles")
        c.stop_after_minutes = self._read_optional_float("stop_after_minutes")
        c.pause_after_minutes = self._read_optional_float("pause_after_minutes")
        c.clicks_per_cycle = self._read_int("clicks_per_cycle", c.clicks_per_cycle)
        c.start_full_grown = self.start_full_grown_var.get()
        c.cost_per_cycle = self._read_int("cost_per_cycle", c.cost_per_cycle)
        c.reward_per_cycle = self._read_int("reward_per_cycle", c.reward_per_cycle)
        c.coin_goal = self._read_optional_int("coin_goal")

    def _refresh_ui_from_state(self):
        """Refresh UI from state object."""
        g = self.state_obj.grid
        t = self.state_obj.timing
        c = self.state_obj.counters

        self.vars["origin_x"].set(str(g.origin_x))
        self.vars["origin_y"].set(str(g.origin_y))
        self.vars["step_x"].set(str(g.step_x))
        self.vars["step_y"].set(str(g.step_y))
        self.vars["rows"].set(str(g.rows))
        self.vars["cols"].set(str(g.cols))
        self.vars["offset_dx"].set(str(g.offset_dx))
        self.vars["offset_dy"].set(str(g.offset_dy))
        self.vars["random_offset_px"].set(str(g.random_offset_px))

        self.vars["cooldown_seconds"].set(str(t.cooldown_seconds))
        self.vars["click_delay"].set(str(t.click_delay))
        self.vars["between_positions_delay"].set(str(t.between_positions_delay))
        self.vars["click_delay_jitter"].set(str(t.click_delay_jitter))
        self.vars["between_positions_jitter"].set(str(t.between_positions_jitter))
        self.always_second_click_var.set(t.always_second_click)

        self.vars["start_cycles_done"].set(str(c.start_cycles_done))
        self.vars["target_cycles"].set("" if c.target_cycles is None else str(c.target_cycles))
        self.vars["pause_at_cycles"].set("" if c.pause_at_cycles is None else str(c.pause_at_cycles))
        self.vars["stop_after_minutes"].set("" if c.stop_after_minutes is None else str(c.stop_after_minutes))
        self.vars["pause_after_minutes"].set("" if c.pause_after_minutes is None else str(c.pause_after_minutes))
        self.vars["clicks_per_cycle"].set(str(c.clicks_per_cycle))
        self.start_full_grown_var.set(c.start_full_grown)
        self.vars["cost_per_cycle"].set(str(c.cost_per_cycle))
        self.vars["reward_per_cycle"].set(str(c.reward_per_cycle))
        self.vars["coin_goal"].set("" if c.coin_goal is None else str(c.coin_goal))

    def save_to_disk(self):
        """Save state to disk."""
        self._sync_state_from_ui()
        save_state(self.state_obj)
        self.append_log("Configuration saved.")

    def load_from_disk(self):
        """Load state from disk."""
        self.state_obj = load_state()
        self._refresh_ui_from_state()
        self.theme_manager.apply_theme(self.state_obj.theme)
        self._update_theme_button()
        self.update_previews()
        self.append_log("Configuration loaded.")

    # -------------------------------------------------------------------------
    # Controls
    # -------------------------------------------------------------------------

    def start(self):
        """Start the auto-clicker."""
        if self.worker_thread and self.worker_thread.is_alive():
            self.append_log("Already running.")
            return

        self._sync_state_from_ui()
        save_state(self.state_obj)

        # Switch to activity tab
        self.nb.select(self.tab_activity)

        # Reset events
        stop_event.clear()
        pause_event.clear()

        # Disable start button
        self.btn_start.configure(state="disabled")

        # Show countdown overlay
        def on_complete():
            self.worker_thread = threading.Thread(target=self._run_worker, daemon=True)
            self.worker_thread.start()
            self.status_bar.set_state("RUNNING")

        def on_cancel():
            stop_event.set()
            self.btn_start.configure(state="normal")
            self.append_log("Start cancelled.")

        CountdownOverlay(self, 3, on_complete, on_cancel)

    def _run_worker(self):
        """Worker thread entry point."""
        try:
            run_cycles(self.state_obj)
        except pyautogui.FailSafeException:
            self.append_log("[STOP] FailSafe triggered (mouse in corner).")
            stop_event.set()
        except Exception as e:
            self.append_log(f"[ERROR] {e}")
            stop_event.set()
        finally:
            with runtime_lock:
                self.state_obj.last_session_cycles_added = session_cycles_added
                self.state_obj.last_session_clicks = session_clicks
                self.state_obj.last_run_timestamp = time.time()
            save_state(self.state_obj)

            self.after(0, self._on_worker_done)

    def _on_worker_done(self):
        """Called when worker thread completes."""
        self.btn_start.configure(state="normal")
        self.status_bar.set_state("STOPPED")

    def pause(self):
        """Pause execution."""
        pause_event.set()
        self.status_bar.set_state("PAUSED")
        self.append_log("Paused.")

    def resume(self):
        """Resume execution."""
        pause_event.clear()
        if self.worker_thread and self.worker_thread.is_alive():
            self.status_bar.set_state("RUNNING")
        self.append_log("Resumed.")

    def stop(self):
        """Stop execution."""
        stop_event.set()
        self.append_log("Stop requested.")

        with runtime_lock:
            self.state_obj.last_session_cycles_added = session_cycles_added
            self.state_obj.last_session_clicks = session_clicks
            self.state_obj.last_run_timestamp = time.time()
        save_state(self.state_obj)

        self.btn_start.configure(state="normal")
        self.status_bar.set_state("STOPPED")

    # -------------------------------------------------------------------------
    # Dashboard Refresh
    # -------------------------------------------------------------------------

    def _refresh_loop(self):
        """Periodic refresh of status bar and dashboard."""
        self._update_dashboard()
        self.after(200, self._refresh_loop)

    def _update_dashboard(self):
        """Update dashboard with current stats."""
        c = self.state_obj.counters

        with runtime_lock:
            clicks = session_clicks
            cycles = session_cycles_added
            pause_time = session_pause_time
            active_time = session_active_time

        total_cycles = c.start_cycles_done + cycles
        target = c.target_cycles

        # Calculate elapsed time
        elapsed = 0.0
        if run_start_time:
            elapsed = time.monotonic() - run_start_time

        # Update status bar
        self.status_bar.update_progress(clicks, total_cycles, target, elapsed)

        # Update dashboard progress
        if target and target > 0:
            pct = min(100, (total_cycles / target) * 100)
            self.dash_progress["value"] = pct
            self.dash_progress_pct.configure(text=f"{pct:.1f}%")
            remaining = max(0, target - total_cycles)
            self.dash_progress_text.configure(
                text=f"Cycles: {total_cycles} / {target} | Remaining: {remaining}"
            )
        else:
            self.dash_progress["value"] = 0
            self.dash_progress_pct.configure(text="--")
            self.dash_progress_text.configure(text=f"Cycles: {total_cycles} / -- | Remaining: --")

        # Time stats
        def fmt_time(seconds):
            h, r = divmod(int(seconds), 3600)
            m, s = divmod(r, 60)
            return f"{h:02d}:{m:02d}:{s:02d}"

        self.dash_runtime.configure(text=fmt_time(elapsed))
        self.dash_active.configure(text=fmt_time(active_time))
        self.dash_paused.configure(text=fmt_time(pause_time))

        # ETA calculation
        if cycles > 0 and target and target > total_cycles and active_time > 0:
            cycles_remaining = target - total_cycles
            rate = cycles / active_time  # cycles per second
            if rate > 0:
                eta_seconds = cycles_remaining / rate
                self.dash_eta.configure(text=fmt_time(eta_seconds))
            else:
                self.dash_eta.configure(text="--:--:--")
        else:
            self.dash_eta.configure(text="--:--:--")

        # Click stats
        self.dash_clicks.configure(text=f"{clicks:,}")
        self.dash_cycles.configure(text=f"{cycles:,}")

        if active_time > 0:
            cpm = (clicks / active_time) * 60
            cypm = (cycles / active_time) * 60
            self.dash_cpm.configure(text=f"{cpm:.1f}")
            self.dash_cypm.configure(text=f"{cypm:.2f}")
        else:
            self.dash_cpm.configure(text="0")
            self.dash_cypm.configure(text="0")

        # Economy stats
        cost = c.cost_per_cycle
        reward = c.reward_per_cycle
        net = reward - cost

        total_spent = cycles * cost
        total_earned = cycles * reward
        total_profit = cycles * net

        self.dash_spent.configure(text=f"{total_spent:,}")
        self.dash_earned.configure(text=f"{total_earned:,}")

        colors = self.theme_manager.get_colors()
        profit_color = colors["success"] if total_profit >= 0 else colors["error"]
        self.dash_profit.configure(text=f"{total_profit:+,}", fg=profit_color)

        # Cycles to goal
        if c.coin_goal and net > 0:
            current_profit = total_profit
            remaining_profit = c.coin_goal - current_profit
            if remaining_profit > 0:
                cycles_needed = int(remaining_profit / net) + 1
                self.dash_goal_cycles.configure(text=f"{cycles_needed:,}")
            else:
                self.dash_goal_cycles.configure(text="Goal reached!")
        else:
            self.dash_goal_cycles.configure(text="--")

    # -------------------------------------------------------------------------
    # About Dialog
    # -------------------------------------------------------------------------

    def _show_about(self):
        """Show the About dialog."""
        colors = self.theme_manager.get_colors()

        about = tk.Toplevel(self)
        about.title(f"About {APP_NAME}")
        about.geometry("420x320")
        about.resizable(False, False)
        about.transient(self)
        about.grab_set()
        about.configure(bg=colors["bg"])

        # Center on parent
        about.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 420) // 2
        y = self.winfo_y() + (self.winfo_height() - 320) // 2
        about.geometry(f"+{x}+{y}")

        # Content
        tk.Label(about, text=APP_NAME, font=("Segoe UI", 20, "bold"),
                bg=colors["bg"], fg=colors["fg"]).pack(pady=(30, 5))

        tk.Label(about, text=f"Version {VERSION}", font=("Segoe UI", 11),
                bg=colors["bg"], fg=colors["text_muted"]).pack()

        tk.Label(about, text=f"Build: {BUILD_DATE}", font=("Segoe UI", 10),
                bg=colors["bg"], fg=colors["text_muted"]).pack(pady=(0, 20))

        desc = """A configurable grid-based auto-clicker
for automating repetitive clicking tasks.

Hotkeys:
  ESC  - Stop immediately
  F8   - Pause/Resume toggle
  F9   - Calibration capture

Made with Python + Tkinter"""

        tk.Label(about, text=desc, font=("Segoe UI", 10),
                bg=colors["bg"], fg=colors["fg"], justify="center").pack(pady=10)

        tk.Button(about, text="Close", command=about.destroy,
                 bg=colors["accent"], fg="#ffffff",
                 activebackground=colors["accent_hover"], activeforeground="#ffffff",
                 relief="flat", padx=30, pady=8, font=("Segoe UI", 10)).pack(pady=20)

    # -------------------------------------------------------------------------
    # Window Close
    # -------------------------------------------------------------------------

    def on_close(self):
        """Handle window close."""
        self.stop()
        self.destroy()


# =============================================================================
# Main Entry
# =============================================================================

if __name__ == "__main__":
    app = App()
    app.mainloop()
