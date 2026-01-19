"""
autoclicker_grid_V1.py
Auto-clicker grille (OS-level) + Interface Tkinter

Fonctions:
- Onglets: Grille / Timers / Compteurs / Log
- Start / Pause / Resume / Stop
- Hotkeys:
  - ESC : Stop immédiat
  - F8  : Pause/Resume (toggle)
  - F9  : Capture calibration (Option B)

Calibration Option B (recommandée):
- Dans l'onglet Grille -> clique "Armer point (0,0)" (ou (0,1), (1,0))
- Va sur le jeu, place la souris au centre de la tuile
- Appuie F9
- L'app calcule origin_x/y, step_x, step_y automatiquement dès qu'elle a les points

Dépendances:
  pip install pyautogui pynput

Notes:
- pyautogui.FAILSAFE = True => bouge la souris dans un coin pour déclencher l'arrêt (FailSafeException)
"""

import json
import time
import threading
import random
import statistics
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Tuple, Optional, Callable

import pyautogui
from pynput import keyboard

import tkinter as tk
from tkinter import ttk


# =============================================================================
# Persistence
# =============================================================================

STATE_FILE = Path("autoclicker_state.json")


# =============================================================================
# Config models
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

    # Spread du clic autour du centre (pixels) -> déplacé ici (Grille)
    random_offset_px: int = 20


@dataclass
class TimingConfig:
    # cooldown par tuile (en secondes)
    cooldown_seconds: float = 8.0

    # Si True, on exécute toujours un 2e clic (ta simplification)
    always_second_click: bool = True

    click_delay: float = 0.16
    between_tiles_delay: float = 0.20
    click_delay_jitter: float = 0.06
    between_tiles_jitter: float = 0.15


@dataclass
class CounterConfig:
    # Reprise: nombre de pelles déjà faites (ex: 80 si tu reprends à 80/250)
    start_shovels_done: int = 0

    # Cible: stop auto quand total_shovels_done >= target_shovels
    target_shovels: Optional[int] = None  # ex: 250

    # Pause auto optionnelle sur total pelles
    pause_at_shovels: Optional[int] = None

    # Pause/Stop auto par durée (minutes)
    stop_after_minutes: Optional[float] = None
    pause_after_minutes: Optional[float] = None

    # Stats console (moyenne glissante)
    stats_window: int = 20

    # Logique pelle: tous les 3 harvests PAR TUILE, en commençant à 1
    harvests_per_shovel: int = 3
    start_full_grown: bool = True  # explicite; dans ton cas True


@dataclass
class AppState:
    grid: GridConfig
    timing: TimingConfig
    counters: CounterConfig

    # Derniers compteurs (persistés)
    last_session_shovels_added: int = 0
    last_session_harvests: int = 0
    last_run_timestamp: float = 0.0


def default_state() -> AppState:
    return AppState(
        grid=GridConfig(),
        timing=TimingConfig(),
        counters=CounterConfig(),
        last_session_shovels_added=0,
        last_session_harvests=0,
        last_run_timestamp=0.0,
    )


def load_state() -> AppState:
    if not STATE_FILE.exists():
        return default_state()

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        st = default_state()

        for group_name in ("grid", "timing", "counters"):
            if group_name in data and isinstance(data[group_name], dict):
                group_obj = getattr(st, group_name)
                for k, v in data[group_name].items():
                    if hasattr(group_obj, k):
                        setattr(group_obj, k, v)

        for k in ("last_session_shovels_added", "last_session_harvests", "last_run_timestamp"):
            if k in data:
                setattr(st, k, data[k])

        return st
    except Exception:
        return default_state()


def save_state(st: AppState) -> None:
    payload = {
        "grid": asdict(st.grid),
        "timing": asdict(st.timing),
        "counters": asdict(st.counters),
        "last_session_shovels_added": st.last_session_shovels_added,
        "last_session_harvests": st.last_session_harvests,
        "last_run_timestamp": st.last_run_timestamp,
    }
    STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# =============================================================================
# Core runtime: clicker + counters
# =============================================================================

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.0

stop_event = threading.Event()
pause_event = threading.Event()

cycle_times = []  # durations of cycles
runtime_lock = threading.Lock()

# runtime counters (session)
session_harvests = 0
session_shovels_added = 0

# per-tile harvest counts
per_tile_harvests: Dict[Tuple[int, int], int] = {}
run_start_time = None

# UI log callback assigned by App
log_fn: Optional[Callable[[str], None]] = None

# Calibration callback + state
calib_fn: Optional[Callable[[str, int, int], None]] = None
calib_armed_point: Optional[str] = None  # "p00" / "p01" / "p10"


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


def random_offset(px: int) -> tuple[int, int]:
    """Random pixel offset in [-px, +px]."""
    if px <= 0:
        return 0, 0
    return random.randint(-px, px), random.randint(-px, px)


def wait_if_paused(step: float = 0.1):
    """Block while paused (ESC still works)."""
    while pause_event.is_set() and not stop_event.is_set():
        time.sleep(step)


def sleep_interruptible(seconds: float, step: float = 0.05):
    """
    Sleep in small slices to:
    - stop quickly on ESC
    - not "consume" waiting time while paused (pause extends the sleep deadline)
    """
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if stop_event.is_set():
            return
        if pause_event.is_set():
            t_pause = time.monotonic()
            wait_if_paused(step=max(step, 0.1))
            end += (time.monotonic() - t_pause)
            continue
        time.sleep(step)


def on_key_press(key):
    """Global hotkeys."""
    global calib_armed_point

    if key == keyboard.Key.esc:
        log("\n[STOP] ESC détecté. Arrêt du script.")
        stop_event.set()

    elif key == keyboard.Key.f8:
        if pause_event.is_set():
            pause_event.clear()
            log("\n[RESUME] Reprise (F8).")
        else:
            pause_event.set()
            log("\n[PAUSE] Pause (F8).")

    elif key == keyboard.Key.f9:
        # Calibration capture (Option B)
        if calib_armed_point is None:
            log("[CALIB] F9 ignoré: aucun point armé. Arme un point dans l'onglet Grille.")
            return

        x, y = pyautogui.position()
        point = calib_armed_point
        calib_armed_point = None

        log(f"[CALIB] Capturé {point} via F9: x={x}, y={y}")

        if calib_fn:
            calib_fn(point, int(x), int(y))


def start_hotkey_listener():
    """Start background keyboard listener."""
    listener = keyboard.Listener(on_press=on_key_press)
    listener.daemon = True
    listener.start()
    return listener


def click_tile(center_x: int, center_y: int, grid: GridConfig, timing: TimingConfig) -> None:
    """
    Click a tile:
    - 1st click = harvest (always)
    - 2nd click = optional simplified replant (timing.always_second_click)
    """
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

    # Between tiles delay (jittered)
    between = jittered(timing.between_tiles_delay, timing.between_tiles_jitter)
    sleep_interruptible(between)


def should_consume_shovel(tile_harvest_count: int, counter_cfg: CounterConfig) -> bool:
    """
    Pelle consommée sur le harvest "full grown".
    Hypothèse: on commence full grown
    => harvest #1, #4, #7... par tuile
    => (h - 1) % 3 == 0
    """
    n = max(1, int(counter_cfg.harvests_per_shovel))
    return ((tile_harvest_count - 1) % n) == 0


def print_stats(counter_cfg: CounterConfig, timing: TimingConfig, base_shovels_done: int):
    """Print cycle stats + counters."""
    if not cycle_times:
        return

    window = cycle_times[-counter_cfg.stats_window:]
    avg = statistics.mean(window)
    mn = min(window)
    mx = max(window)

    with runtime_lock:
        total_shovels_done = base_shovels_done + session_shovels_added
        h = session_harvests
        s = session_shovels_added

    log(f"[STATS] cycles={len(cycle_times)} | avg({len(window)})={avg:.2f}s | min={mn:.2f}s | max={mx:.2f}s")
    log(f"[COUNT] harvests_session={h} | shovels_added_session={s} | shovels_done_total={total_shovels_done}")

    if avg > timing.cooldown_seconds:
        log(f"[INFO] avg > {timing.cooldown_seconds:.1f}s → baisse delays/jitter")
    else:
        log(f"[INFO] avg < {timing.cooldown_seconds:.1f}s → ok (attente résiduelle si besoin).")


def maybe_pause_or_stop(counter_cfg: CounterConfig, base_shovels_done: int):
    """Apply pause/stop rules based on counters + time."""
    global run_start_time

    if run_start_time is None:
        return

    elapsed_minutes = (time.monotonic() - run_start_time) / 60.0

    with runtime_lock:
        total_shovels_done = base_shovels_done + session_shovels_added

    # STOP by target shovels
    if counter_cfg.target_shovels is not None and total_shovels_done >= counter_cfg.target_shovels:
        log(f"\n[STOP AUTO] Cible pelles atteinte: {total_shovels_done}/{counter_cfg.target_shovels}")
        stop_event.set()
        return

    # STOP by time
    if counter_cfg.stop_after_minutes is not None and elapsed_minutes >= counter_cfg.stop_after_minutes:
        log(f"\n[STOP AUTO] Temps atteint: {elapsed_minutes:.1f} min / {counter_cfg.stop_after_minutes} min")
        stop_event.set()
        return

    # PAUSE by shovels
    if counter_cfg.pause_at_shovels is not None and total_shovels_done >= counter_cfg.pause_at_shovels:
        if not pause_event.is_set():
            pause_event.set()
            log(f"\n[PAUSE AUTO] Pelles atteinte: {total_shovels_done}/{counter_cfg.pause_at_shovels} (F8 pour reprendre)")
        return

    # PAUSE by time
    if counter_cfg.pause_after_minutes is not None and elapsed_minutes >= counter_cfg.pause_after_minutes:
        if not pause_event.is_set():
            pause_event.set()
            log(f"\n[PAUSE AUTO] Temps atteint: {elapsed_minutes:.1f} min / {counter_cfg.pause_after_minutes} min (F8 pour reprendre)")
        return


def run_cycles(state: AppState):
    """
    Main loop:
    - cooldown par tuile (ready_at par tuile)
    - + un "deadline" global pour ne pas boucler trop vite (sans être obligatoire si tu veux)
    """
    global per_tile_harvests, session_harvests, session_shovels_added, run_start_time, cycle_times

    grid = state.grid
    timing = state.timing
    counter_cfg = state.counters

    base_shovels_done = int(counter_cfg.start_shovels_done)

    origin_x = int(grid.origin_x + grid.offset_dx)
    origin_y = int(grid.origin_y + grid.offset_dy)
    rows = max(1, int(grid.rows))
    cols = max(1, int(grid.cols))

    # Per tile readiness times (per-tile cooldown)
    ready_at = {(r, c): 0.0 for r in range(rows) for c in range(cols)}

    # Per tile harvest count
    per_tile_harvests = {(r, c): 0 for r in range(rows) for c in range(cols)}

    cycle_times = []

    with runtime_lock:
        session_harvests = 0
        session_shovels_added = 0

    run_start_time = time.monotonic()

    cycle = 0
    log("\n=== START === (ESC stop / F8 pause / F9 calibrate)")

    while not stop_event.is_set():
        wait_if_paused()

        cycle += 1
        log(f"\n=== Cycle {cycle} ===")

        t0 = time.monotonic()
        next_start = t0 + float(timing.cooldown_seconds)

        for r in range(rows):
            for c in range(cols):
                if stop_event.is_set():
                    break

                wait_if_paused()

                # Wait until this tile is ready (per tile cooldown)
                now = time.monotonic()
                wait = ready_at[(r, c)] - now
                if wait > 0:
                    sleep_interruptible(wait)
                    if stop_event.is_set():
                        break

                # Compute tile center
                x = origin_x + c * int(grid.step_x)
                y = origin_y + r * int(grid.step_y)

                # Click tile
                click_tile(x, y, grid, timing)

                # Count harvest (one per tile pass)
                with runtime_lock:
                    session_harvests += 1

                # Update per tile harvest count
                per_tile_harvests[(r, c)] += 1
                tile_h = per_tile_harvests[(r, c)]

                # Shovel consumption rule
                if should_consume_shovel(tile_h, counter_cfg):
                    with runtime_lock:
                        session_shovels_added += 1
                        total_shovels_done = base_shovels_done + session_shovels_added
                    log(f"[SHOVEL] Tuile({r},{c}) harvest#{tile_h} → +1 pelle | total={total_shovels_done}")

                # Apply auto pause/stop rules
                maybe_pause_or_stop(counter_cfg, base_shovels_done)
                if stop_event.is_set():
                    break

                # Tile ready again after cooldown
                ready_at[(r, c)] = time.monotonic() + float(timing.cooldown_seconds)

            if stop_event.is_set():
                break

        elapsed = time.monotonic() - t0
        cycle_times.append(elapsed)

        log(f"Cycle en {elapsed:.2f}s")
        print_stats(counter_cfg, timing, base_shovels_done)

        if stop_event.is_set():
            break

        # Global cycle deadline wait (optionnel mais utile pour éviter une relance trop agressive)
        remaining = next_start - time.monotonic()
        if remaining > 0:
            log(f"Attente cooldown global: {remaining:.2f}s")
            sleep_interruptible(remaining)
        else:
            log(f"> cooldown global dépassé (retard de {-remaining:.2f}s), relance direct")

    log("\n=== STOPPED ===")


# =============================================================================
# GUI (Tkinter)
# =============================================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Auto-clicker grille — Config & Counters")
        self.geometry("1020x760")

        # Load saved state
        self.state_obj = load_state()

        # Worker thread
        self.worker_thread: Optional[threading.Thread] = None

        # UI variables
        self.vars: Dict[str, tk.StringVar] = {}
        self._preview_job = None
        self._start_countdown_job = None

        # calibration storage in UI
        self._calib_points: Dict[str, Optional[Tuple[int, int]]] = {"p00": None, "p01": None, "p10": None}

        # Build UI
        self._build_ui()

        # Attach logger (thread-safe via after)
        global log_fn
        log_fn = self.append_log

        # Attach calibration callback (thread-safe via after)
        global calib_fn
        def _calib_dispatch(point: str, x: int, y: int) -> None:
            self.after(0, lambda: self.apply_calibration_point(point, x, y))
            return None
        calib_fn = _calib_dispatch

        # Hotkeys always enabled
        start_hotkey_listener()

        # Live counters refresh
        self.after(200, self.refresh_counters)

        # Auto update previews when fields change
        self.install_preview_traces()
        self.update_previews()

        # Window close handler
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Initial info
        self.append_log("Loaded state from autoclicker_state.json (if exists).")
        self.append_log("Hotkeys: ESC=Stop | F8=Pause/Resume | F9=Calibration capture")

    # -------------------------------------------------------------------------
    # UI helpers
    # -------------------------------------------------------------------------

    def _var(self, name: str, default) -> tk.StringVar:
        v = tk.StringVar(value=str(default))
        self.vars[name] = v
        return v

    def _row(self, parent, r, label, var, width=16):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=8, pady=5)
        ttk.Entry(parent, textvariable=var, width=width).grid(row=r, column=1, sticky="w", padx=8, pady=5)

    def append_log(self, msg: str):
        """Thread-safe: always write into Text via Tk main thread."""
        def _do():
            ts = time.strftime("%H:%M:%S")
            self.log_text.insert("end", f"[{ts}] {msg}\n")
            self.log_text.see("end")
        self.after(0, _do)

    def _read_int(self, name: str, default=0) -> int:
        s = self.vars[name].get().strip()
        if s == "":
            return default
        return int(float(s))

    def _read_float(self, name: str, default=0.0) -> float:
        s = self.vars[name].get().strip()
        if s == "":
            return default
        return float(s)

    def _read_optional_int(self, name: str) -> Optional[int]:
        s = self.vars[name].get().strip()
        if s == "":
            return None
        return int(float(s))

    def _read_optional_float(self, name: str) -> Optional[float]:
        s = self.vars[name].get().strip()
        if s == "":
            return None
        return float(s)

    # -------------------------------------------------------------------------
    # Build UI
    # -------------------------------------------------------------------------

    def _build_ui(self):
        # Top bar
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=10)

        self.btn_start = ttk.Button(top, text="Start", command=self.start)
        self.btn_start.pack(side="left", padx=6)

        ttk.Button(top, text="Pause", command=self.pause).pack(side="left", padx=6)
        ttk.Button(top, text="Resume", command=self.resume).pack(side="left", padx=6)
        ttk.Button(top, text="Stop", command=self.stop).pack(side="left", padx=6)

        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=12)

        ttk.Button(top, text="Load", command=self.load_from_disk).pack(side="left", padx=6)
        ttk.Button(top, text="Save", command=self.save_to_disk).pack(side="left", padx=6)

        # Live counters label (simple)
        self.live_lbl = ttk.Label(
            top,
            text="harvests=0 | shovels_added=0 | shovels_total=0",
            font=("Segoe UI", 10, "bold"),
        )
        self.live_lbl.pack(side="right")

        # Notebook + tabs
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=8)

        self.tab_grid = ttk.Frame(self.nb)
        self.tab_timers = ttk.Frame(self.nb)
        self.tab_counters = ttk.Frame(self.nb)
        self.tab_log = ttk.Frame(self.nb)

        self.nb.add(self.tab_grid, text="Grille")
        self.nb.add(self.tab_timers, text="Timers")
        self.nb.add(self.tab_counters, text="Compteurs")
        self.nb.add(self.tab_log, text="Log")

        self._build_grid_tab(self.tab_grid)
        self._build_timers_tab(self.tab_timers)
        self._build_counters_tab(self.tab_counters)
        self._build_log_tab(self.tab_log)

    def _build_grid_tab(self, parent):
        g = self.state_obj.grid

        # Grid fields
        self._row(parent, 0, "origin_x", self._var("origin_x", g.origin_x))
        self._row(parent, 1, "origin_y", self._var("origin_y", g.origin_y))
        self._row(parent, 2, "step_x", self._var("step_x", g.step_x))
        self._row(parent, 3, "step_y", self._var("step_y", g.step_y))
        self._row(parent, 4, "rows", self._var("rows", g.rows))
        self._row(parent, 5, "cols", self._var("cols", g.cols))
        self._row(parent, 6, "offset_dx", self._var("offset_dx", g.offset_dx))
        self._row(parent, 7, "offset_dy", self._var("offset_dy", g.offset_dy))

        # Random offset moved here
        self._row(parent, 8, "random_offset_px", self._var("random_offset_px", g.random_offset_px))

        ttk.Separator(parent, orient="horizontal").grid(row=9, column=0, columnspan=3, sticky="ew", pady=10)

        ttk.Label(parent, text="Aperçu grille + spread clic (random_offset_px)", font=("Segoe UI", 10, "bold"))\
            .grid(row=10, column=0, columnspan=2, sticky="w", padx=8)

        self.grid_preview = tk.Canvas(parent, width=520, height=320, bg="white",
                                      highlightthickness=1, highlightbackground="#ddd")
        self.grid_preview.grid(row=11, column=0, columnspan=2, sticky="w", padx=8, pady=8)

        ttk.Label(parent, text="Note: la zone bleue représente ±random_offset_px autour du centre de chaque tuile.")\
            .grid(row=12, column=0, columnspan=2, sticky="w", padx=8, pady=3)

        # Calibration block (Option B: F9)
        ttk.Separator(parent, orient="horizontal").grid(row=13, column=0, columnspan=3, sticky="ew", pady=10)

        ttk.Label(parent, text="Calibration (Option B: Hotkey F9)", font=("Segoe UI", 10, "bold"))\
            .grid(row=14, column=0, columnspan=2, sticky="w", padx=8)

        ttk.Label(parent, text="1) Clique 'Armer', 2) va dans le jeu, place la souris sur la tuile, 3) appuie F9.")\
            .grid(row=15, column=0, columnspan=2, sticky="w", padx=8, pady=2)

        btns = ttk.Frame(parent)
        btns.grid(row=16, column=0, columnspan=2, sticky="w", padx=8, pady=6)

        ttk.Button(btns, text="Armer point (0,0)", command=lambda: self.arm_calibration("p00")).pack(side="left", padx=4)
        ttk.Button(btns, text="Armer point (0,1) (droite)", command=lambda: self.arm_calibration("p01")).pack(side="left", padx=4)
        ttk.Button(btns, text="Armer point (1,0) (bas)", command=lambda: self.arm_calibration("p10")).pack(side="left", padx=4)

        self.calib_status = ttk.Label(parent, text="Points: (0,0)=—  (0,1)=—  (1,0)=—", foreground="#111827")
        self.calib_status.grid(row=17, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        ttk.Button(parent, text="Reset calibration", command=self.reset_calibration)\
            .grid(row=18, column=0, sticky="w", padx=8, pady=4)

    def _build_timers_tab(self, parent):
        t = self.state_obj.timing

        self._row(parent, 0, "cooldown_seconds", self._var("cooldown_seconds", t.cooldown_seconds))
        self._row(parent, 1, "click_delay", self._var("click_delay", t.click_delay))
        self._row(parent, 2, "between_tiles_delay", self._var("between_tiles_delay", t.between_tiles_delay))
        self._row(parent, 3, "click_delay_jitter", self._var("click_delay_jitter", t.click_delay_jitter))
        self._row(parent, 4, "between_tiles_jitter", self._var("between_tiles_jitter", t.between_tiles_jitter))

        self.always_second_click_var = tk.BooleanVar(value=bool(t.always_second_click))
        ttk.Checkbutton(parent, text="Toujours faire le 2e clic (simplification)", variable=self.always_second_click_var)\
            .grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=6)

        ttk.Separator(parent, orient="horizontal").grid(row=6, column=0, columnspan=3, sticky="ew", pady=10)

        ttk.Label(parent, text="Aperçu timings + estimation cycle (min/max)", font=("Segoe UI", 10, "bold"))\
            .grid(row=7, column=0, columnspan=2, sticky="w", padx=8)

        self.timing_preview = tk.Canvas(parent, width=700, height=140, bg="white",
                                        highlightthickness=1, highlightbackground="#ddd")
        self.timing_preview.grid(row=8, column=0, columnspan=2, sticky="w", padx=8, pady=8)

        self.timing_label = ttk.Label(parent, text="", foreground="#111827")
        self.timing_label.grid(row=9, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        ttk.Label(
            parent,
            text="Lecture: la timeline montre l'intervalle du click_delay (entre clic1 et clic2) + between_tiles.\n"
                 "Les valeurs 'Traverse' = somme sur toutes les tuiles (sans compter les waits par tuile).",
            foreground="#444"
        ).grid(row=10, column=0, columnspan=2, sticky="w", padx=8, pady=6)

    def _build_counters_tab(self, parent):
        c = self.state_obj.counters

        self._row(parent, 0, "start_shovels_done (déjà fait)", self._var("start_shovels_done", c.start_shovels_done))
        self._row(parent, 1, "target_shovels (cible stop)", self._var("target_shovels", "" if c.target_shovels is None else c.target_shovels))
        self._row(parent, 2, "pause_at_shovels", self._var("pause_at_shovels", "" if c.pause_at_shovels is None else c.pause_at_shovels))

        self._row(parent, 3, "stop_after_minutes", self._var("stop_after_minutes", "" if c.stop_after_minutes is None else c.stop_after_minutes))
        self._row(parent, 4, "pause_after_minutes", self._var("pause_after_minutes", "" if c.pause_after_minutes is None else c.pause_after_minutes))

        self._row(parent, 5, "harvests_per_shovel", self._var("harvests_per_shovel", c.harvests_per_shovel))
        self._row(parent, 6, "stats_window", self._var("stats_window", c.stats_window))

        self.start_full_grown_var = tk.BooleanVar(value=bool(c.start_full_grown))
        ttk.Checkbutton(parent, text="Start full grown (pelle sur harvest #1, #4, #7...)", variable=self.start_full_grown_var)\
            .grid(row=7, column=0, columnspan=2, sticky="w", padx=8, pady=6)

        ttk.Label(
            parent,
            text="Ex: déjà fait=80, cible=250 → stop auto à 250.\n"
                 "Stop quand: start_shovels_done + shovels_added_session >= target_shovels.",
            foreground="#444"
        ).grid(row=8, column=0, columnspan=2, sticky="w", padx=8, pady=8)

    def _build_log_tab(self, parent):
        # Dashboard au-dessus des logs
        dash = ttk.Frame(parent)
        dash.pack(fill="x", padx=8, pady=(8, 4))

        self.dash_lbl1 = ttk.Label(dash, text="Session: harvests=0 | shovels_added=0", font=("Segoe UI", 10, "bold"))
        self.dash_lbl1.pack(anchor="w")

        self.dash_lbl2 = ttk.Label(dash, text="Progress: start=0 | target=— | total=0 | remaining=—", foreground="#374151")
        self.dash_lbl2.pack(anchor="w", pady=(2, 0))

        self.dash_lbl3 = ttk.Label(dash, text="Auto: pause_at=— | stop_after=— min | pause_after=— min", foreground="#6b7280")
        self.dash_lbl3.pack(anchor="w", pady=(2, 0))

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=8, pady=6)

        self.log_text = tk.Text(parent, height=12, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # -------------------------------------------------------------------------
    # Previews (Grid + Timers)
    # -------------------------------------------------------------------------

    def install_preview_traces(self):
        keys = [
            # grid
            "origin_x", "origin_y", "step_x", "step_y", "rows", "cols", "offset_dx", "offset_dy", "random_offset_px",
            # timers
            "cooldown_seconds", "click_delay", "between_tiles_delay", "click_delay_jitter", "between_tiles_jitter",
        ]
        for k in keys:
            if k in self.vars:
                self.vars[k].trace_add("write", lambda *_: self.schedule_preview_update())

        self.always_second_click_var.trace_add("write", lambda *_: self.schedule_preview_update())
        self.start_full_grown_var.trace_add("write", lambda *_: self.schedule_preview_update())

    def schedule_preview_update(self):
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(120, self.update_previews)

    def update_previews(self):
        self._preview_job = None
        if hasattr(self, "grid_preview"):
            self.update_grid_preview()
        if hasattr(self, "timing_preview"):
            self.update_timing_preview()

    def update_grid_preview(self):
        cv = self.grid_preview
        cv.delete("all")

        origin_x = self._read_int("origin_x", 0) + self._read_int("offset_dx", 0)
        origin_y = self._read_int("origin_y", 0) + self._read_int("offset_dy", 0)
        step_x = max(1, self._read_int("step_x", 1))
        step_y = max(1, self._read_int("step_y", 1))
        rows = max(1, self._read_int("rows", 1))
        cols = max(1, self._read_int("cols", 1))
        spread = max(0, self._read_int("random_offset_px", 0))

        w = int(cv["width"])
        h = int(cv["height"])
        margin = 20

        # bounding box in "screen coords"
        min_x = origin_x - spread
        min_y = origin_y - spread
        max_x = origin_x + (cols - 1) * step_x + spread
        max_y = origin_y + (rows - 1) * step_y + spread

        bw = max(1, max_x - min_x)
        bh = max(1, max_y - min_y)

        # scale to fit canvas
        sx = (w - 2 * margin) / bw
        sy = (h - 2 * margin) / bh
        s = min(sx, sy)

        def tx(x):
            return margin + (x - min_x) * s

        def ty(y):
            return margin + (y - min_y) * s

        cv.create_rectangle(2, 2, w - 2, h - 2, outline="#eee")

        for r in range(rows):
            for c in range(cols):
                cx = origin_x + c * step_x
                cy = origin_y + r * step_y

                x = tx(cx)
                y = ty(cy)

                if spread > 0:
                    x1 = tx(cx - spread)
                    y1 = ty(cy - spread)
                    x2 = tx(cx + spread)
                    y2 = ty(cy + spread)
                    cv.create_rectangle(x1, y1, x2, y2, outline="#93c5fd", fill="")

                cv.create_oval(x - 2, y - 2, x + 2, y + 2, fill="#2563eb", outline="")
                cv.create_text(x + 14, y - 12, text=f"{r},{c}", fill="#6b7280", font=("Segoe UI", 8))

        cv.create_text(
            margin, h - 10, anchor="w",
            text=f"origin({origin_x},{origin_y}) step({step_x},{step_y}) spread ±{spread}px | tiles={rows}x{cols}",
            fill="#111827", font=("Segoe UI", 9)
        )

    def update_timing_preview(self):
        cv = self.timing_preview
        cv.delete("all")

        cooldown = max(0.0, self._read_float("cooldown_seconds", 0.0))
        click_delay = max(0.0, self._read_float("click_delay", 0.0))
        click_j = max(0.0, self._read_float("click_delay_jitter", 0.0))
        between = max(0.0, self._read_float("between_tiles_delay", 0.0))
        between_j = max(0.0, self._read_float("between_tiles_jitter", 0.0))

        rows = max(1, self._read_int("rows", 1))
        cols = max(1, self._read_int("cols", 1))
        ntiles = rows * cols

        second_click = bool(self.always_second_click_var.get())

        cd_min = max(0.0, click_delay - click_j) if second_click else 0.0
        cd_max = (click_delay + click_j) if second_click else 0.0
        bt_min = max(0.0, between - between_j)
        bt_max = between + between_j

        per_tile_min = cd_min + bt_min
        per_tile_max = cd_max + bt_max

        traverse_min = ntiles * per_tile_min
        traverse_max = ntiles * per_tile_max

        cycle_min = max(cooldown, traverse_min)
        cycle_max = max(cooldown, traverse_max)

        w = int(cv["width"])
        h = int(cv["height"])
        margin = 18
        baseline_y = h // 2

        cv.create_rectangle(2, 2, w - 2, h - 2, outline="#eee")

        tmax = max(0.001, per_tile_max)

        def x(t):
            return margin + (w - 2 * margin) * (t / tmax)

        cv.create_line(margin, baseline_y, w - margin, baseline_y, fill="#e5e7eb", width=2)
        cv.create_text(margin, baseline_y - 18, text="click1", fill="#2563eb", font=("Segoe UI", 8))
        cv.create_line(margin, baseline_y - 10, margin, baseline_y + 10, fill="#2563eb", width=2)

        if second_click:
            x1 = x(cd_min)
            x2 = x(cd_max)
            cv.create_rectangle(x1, baseline_y - 14, x2, baseline_y + 14, outline="#93c5fd", fill="#dbeafe")
            cv.create_text((x1 + x2) / 2, baseline_y - 26, text="click2 (range)", fill="#1f2937", font=("Segoe UI", 8))
            cv.create_line(x(cd_max), baseline_y - 12, x(cd_max), baseline_y + 12, fill="#2563eb", width=2)

        end_min = cd_min + bt_min
        end_max = cd_max + bt_max
        cv.create_rectangle(x(end_min), baseline_y - 14, x(end_max), baseline_y + 14, outline="#cbd5e1", fill="#f1f5f9")
        cv.create_text((x(end_min) + x(end_max)) / 2, baseline_y + 26, text="end tile (range)", fill="#1f2937", font=("Segoe UI", 8))

        self.timing_label.configure(
            text=(
                f"Par tuile: {per_tile_min:.2f}s → {per_tile_max:.2f}s | "
                f"Traverse ({ntiles} tuiles): {traverse_min:.2f}s → {traverse_max:.2f}s | "
                f"Cycle estimé (cooldown={cooldown:.2f}s): {cycle_min:.2f}s → {cycle_max:.2f}s"
            )
        )

    # -------------------------------------------------------------------------
    # Calibration (Option B: F9)
    # -------------------------------------------------------------------------

    def arm_calibration(self, point_name: str):
        global calib_armed_point
        calib_armed_point = point_name
        name = {"p00": "(0,0)", "p01": "(0,1)", "p10": "(1,0)"}.get(point_name, point_name)
        self.append_log(f"[CALIB] Point {name} armé. Va dans le jeu, place la souris, puis F9.")
        self._update_calib_status(armed=point_name)

    def reset_calibration(self):
        global calib_armed_point
        calib_armed_point = None
        self._calib_points = {"p00": None, "p01": None, "p10": None}
        self._update_calib_status()
        self.append_log("[CALIB] Reset des points de calibration.")

    def apply_calibration_point(self, point_name: str, x: int, y: int):
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

        self.append_log(f"[CALIB] Appliqué {point_name}: ({x},{y}). origin/step mis à jour si possible.")
        self._update_calib_status()
        self.update_previews()

    def _update_calib_status(self, armed: Optional[str] = None):
        p00 = self._calib_points.get("p00")
        p01 = self._calib_points.get("p01")
        p10 = self._calib_points.get("p10")

        def fmt(p):
            return "—" if not p else f"{p[0]},{p[1]}"

        armed_txt = ""
        if armed:
            armed_txt = f" | ARMÉ: {armed} (F9)"

        self.calib_status.configure(
            text=f"Points: (0,0)={fmt(p00)}  (0,1)={fmt(p01)}  (1,0)={fmt(p10)}{armed_txt}"
        )

    # -------------------------------------------------------------------------
    # State sync + persistence
    # -------------------------------------------------------------------------

    def sync_state_from_ui(self):
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
        t.between_tiles_delay = self._read_float("between_tiles_delay", t.between_tiles_delay)
        t.click_delay_jitter = self._read_float("click_delay_jitter", t.click_delay_jitter)
        t.between_tiles_jitter = self._read_float("between_tiles_jitter", t.between_tiles_jitter)
        t.always_second_click = bool(self.always_second_click_var.get())

        c = self.state_obj.counters
        c.start_shovels_done = self._read_int("start_shovels_done", c.start_shovels_done)
        c.target_shovels = self._read_optional_int("target_shovels")
        c.pause_at_shovels = self._read_optional_int("pause_at_shovels")
        c.stop_after_minutes = self._read_optional_float("stop_after_minutes")
        c.pause_after_minutes = self._read_optional_float("pause_after_minutes")
        c.harvests_per_shovel = self._read_int("harvests_per_shovel", c.harvests_per_shovel)
        c.stats_window = self._read_int("stats_window", c.stats_window)
        c.start_full_grown = bool(self.start_full_grown_var.get())

    def save_to_disk(self):
        self.sync_state_from_ui()
        save_state(self.state_obj)
        self.append_log("Saved to disk.")

    def load_from_disk(self):
        self.state_obj = load_state()
        self.append_log("Loaded from disk.")
        self._refresh_ui_from_state()
        self.update_previews()

    def _refresh_ui_from_state(self):
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
        self.vars["between_tiles_delay"].set(str(t.between_tiles_delay))
        self.vars["click_delay_jitter"].set(str(t.click_delay_jitter))
        self.vars["between_tiles_jitter"].set(str(t.between_tiles_jitter))
        self.always_second_click_var.set(bool(t.always_second_click))

        self.vars["start_shovels_done"].set(str(c.start_shovels_done))
        self.vars["target_shovels"].set("" if c.target_shovels is None else str(c.target_shovels))
        self.vars["pause_at_shovels"].set("" if c.pause_at_shovels is None else str(c.pause_at_shovels))
        self.vars["stop_after_minutes"].set("" if c.stop_after_minutes is None else str(c.stop_after_minutes))
        self.vars["pause_after_minutes"].set("" if c.pause_after_minutes is None else str(c.pause_after_minutes))
        self.vars["harvests_per_shovel"].set(str(c.harvests_per_shovel))
        self.vars["stats_window"].set(str(c.stats_window))
        self.start_full_grown_var.set(bool(c.start_full_grown))

    # -------------------------------------------------------------------------
    # Controls: Start/Pause/Resume/Stop
    # -------------------------------------------------------------------------

    def start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self.append_log("Déjà en cours.")
            return

        self.sync_state_from_ui()
        save_state(self.state_obj)

        # Auto switch to Log tab
        self.nb.select(self.tab_log)

        stop_event.clear()
        pause_event.clear()

        self.btn_start.config(state="disabled")

        self.append_log("Start in 3 seconds... place ton jeu au bon endroit.")
        self._start_countdown(3)

    def _start_countdown(self, n: int):
        if stop_event.is_set():
            self.btn_start.config(state="normal")
            return

        if n <= 0:
            self.append_log("GO!")
            self.worker_thread = threading.Thread(target=self._run_worker, daemon=True)
            self.worker_thread.start()
            return

        self.append_log(f"{n}...")
        self._start_countdown_job = self.after(1000, lambda: self._start_countdown(n - 1))

    def _run_worker(self):
        try:
            run_cycles(self.state_obj)
        except pyautogui.FailSafeException:
            self.append_log("[STOP] FailSafe déclenché (souris dans un coin). Arrêt propre.")
            stop_event.set()
        except KeyboardInterrupt:
            self.append_log("[STOP] Ctrl+C détecté. Arrêt propre.")
            stop_event.set()
        finally:
            with runtime_lock:
                self.state_obj.last_session_shovels_added = session_shovels_added
                self.state_obj.last_session_harvests = session_harvests
                self.state_obj.last_run_timestamp = time.time()
            save_state(self.state_obj)

            self.after(0, lambda: self.btn_start.config(state="normal"))

    def pause(self):
        pause_event.set()
        self.append_log("Pause (GUI).")

    def resume(self):
        pause_event.clear()
        self.append_log("Resume (GUI).")

    def stop(self):
        stop_event.set()
        self.append_log("Stop demandé (GUI).")

        with runtime_lock:
            self.state_obj.last_session_shovels_added = session_shovels_added
            self.state_obj.last_session_harvests = session_harvests
            self.state_obj.last_run_timestamp = time.time()
        save_state(self.state_obj)

        self.btn_start.config(state="normal")

    def refresh_counters(self):
        c = self.state_obj.counters
        with runtime_lock:
            total = int(c.start_shovels_done) + session_shovels_added
            h = session_harvests
            s = session_shovels_added

        target = c.target_shovels
        remaining = "—"
        if target is not None:
            remaining = max(0, target - total)

        self.live_lbl.configure(text=f"harvests={h} | shovels_added={s} | shovels_total={total}")

        # dashboard log tab
        self.dash_lbl1.configure(text=f"Session: harvests={h} | shovels_added={s}")
        self.dash_lbl2.configure(text=f"Progress: start={c.start_shovels_done} | target={target if target is not None else '—'} | total={total} | remaining={remaining}")
        self.dash_lbl3.configure(text=f"Auto: pause_at={c.pause_at_shovels if c.pause_at_shovels is not None else '—'} | stop_after={c.stop_after_minutes if c.stop_after_minutes is not None else '—'} min | pause_after={c.pause_after_minutes if c.pause_after_minutes is not None else '—'} min")

        self.after(200, self.refresh_counters)

    def on_close(self):
        self.stop()
        self.destroy()


# =============================================================================
# Main entry
# =============================================================================

if __name__ == "__main__":
    log("Launching UI...")
    app = App()
    app.mainloop()
