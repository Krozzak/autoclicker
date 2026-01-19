import time
import threading
import random
import statistics
import pyautogui
from pynput import keyboard

# =============== CONFIG (à modifier facilement) ===============
COOLDOWN_SECONDS = 10.0          # délai entre chaque "harvest cycle"
DOUBLE_CLICK = True             # 2 clics par tuile (harvest + replant simplifié)
CLICK_DELAY = 0.16             # petite pause entre les clics
BETWEEN_TILES_DELAY = 0.20      # pause entre tuiles (évite de saturer)

# Variabilité (jitter) sur les timings
# Exemple: 0.03 => ajoute un aléa uniforme entre -0.03 et +0.03
CLICK_DELAY_JITTER = 0.06
BETWEEN_TILES_JITTER = 0.15

# Variabilité sur la position (pixels)
# Exemple: 3 => clique dans un carré [-3..+3] px autour du centre
RANDOM_OFFSET_PX = 20

# Grille: position du centre de la tuile (0,0) et pas entre tuiles
GRID = {
    "origin_x": 854,   # centre de la tuile en haut-gauche
    "origin_y": 400,
    "step_x": 84,      # distance en pixels entre centres de tuiles (horizontal)
    "step_y": 84,      # distance en pixels entre centres de tuiles (vertical)
    "rows": 5,
    "cols": 4,
}

# Option: décalage si tu veux cliquer un peu plus bas/haut que le centre
OFFSET = {"dx": 0, "dy": 0}

# Stats
STATS_WINDOW = 20  # moyenne glissante sur les N derniers cycles

# ------------------- LIMITES AUTO -------------------
# Mets None pour désactiver
STOP_AFTER_HARVESTS = None      # ex: 2000
PAUSE_AFTER_HARVESTS = None     # ex: 500 (pause auto)

STOP_AFTER_MINUTES = None       # ex: 30
PAUSE_AFTER_MINUTES = None      # ex: 10

STOP_AFTER_SHOVELS = 250       # ex: 150
PAUSE_AFTER_SHOVELS = None      # ex: 50

# Tous les 3 harvests SUR UNE MEME TUILE => 1 pelle + 1 replant
HARVESTS_PER_SHOVEL = 3

# =============== FIN CONFIG ===============

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.0

stop_event = threading.Event()
pause_event = threading.Event()

cycle_times = []  # stocke les durées de cycle

# Compteurs
START_FULL_GROWN = True
total_harvests = 0
total_replants = 0
total_shovels = 0
per_tile_harvests = {}  # (r,c) -> nb harvests sur cette tuile

run_start_time = None

def wait_if_paused(step: float = 0.1):
    """Bloque tant qu'on est en pause (ESC reste prioritaire)."""
    while pause_event.is_set() and not stop_event.is_set():
        time.sleep(step)

def sleep_interruptible(seconds: float, step: float = 0.05):
    """
    Dort en petites tranches pour pouvoir s'arrêter vite avec ESC,
    et ne "consomme" pas le temps de sleep pendant une pause.
    """
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if stop_event.is_set():
            return
        if pause_event.is_set():
            # on attend la reprise, et on décale la deadline du temps passé en pause
            t_pause = time.monotonic()
            wait_if_paused(step=max(step, 0.1))
            end += (time.monotonic() - t_pause)
            continue
        time.sleep(step)

def maybe_pause_or_stop():
    """
    Applique les règles pause/stop automatiques.
    Appelée régulièrement (après chaque harvest, par ex.).
    """
    global total_harvests, total_shovels, run_start_time

    if run_start_time is None:
        return

    elapsed_minutes = (time.monotonic() - run_start_time) / 60.0

    # ----- STOP -----
    if STOP_AFTER_HARVESTS is not None and total_harvests >= STOP_AFTER_HARVESTS:
        print(f"\n[STOP AUTO] Harvests atteint: {total_harvests}/{STOP_AFTER_HARVESTS}")
        stop_event.set()
        return

    if STOP_AFTER_MINUTES is not None and elapsed_minutes >= STOP_AFTER_MINUTES:
        print(f"\n[STOP AUTO] Temps atteint: {elapsed_minutes:.1f} min / {STOP_AFTER_MINUTES} min")
        stop_event.set()
        return

    if STOP_AFTER_SHOVELS is not None and total_shovels >= STOP_AFTER_SHOVELS:
        print(f"\n[STOP AUTO] Pelles atteint: {total_shovels}/{STOP_AFTER_SHOVELS}")
        stop_event.set()
        return

    # ----- PAUSE -----
    if PAUSE_AFTER_HARVESTS is not None and total_harvests >= PAUSE_AFTER_HARVESTS:
        if not pause_event.is_set():
            pause_event.set()
            print(f"\n[PAUSE AUTO] Harvests atteint: {total_harvests}/{PAUSE_AFTER_HARVESTS} (F8 pour reprendre)")
        return

    if PAUSE_AFTER_MINUTES is not None and elapsed_minutes >= PAUSE_AFTER_MINUTES:
        if not pause_event.is_set():
            pause_event.set()
            print(f"\n[PAUSE AUTO] Temps atteint: {elapsed_minutes:.1f} min / {PAUSE_AFTER_MINUTES} min (F8 pour reprendre)")
        return

    if PAUSE_AFTER_SHOVELS is not None and total_shovels >= PAUSE_AFTER_SHOVELS:
        if not pause_event.is_set():
            pause_event.set()
            print(f"\n[PAUSE AUTO] Pelles atteint: {total_shovels}/{PAUSE_AFTER_SHOVELS} (F8 pour reprendre)")
        return

def on_key_press(key):
    # Stop sur ESC
    if key == keyboard.Key.esc:
        print("\n[STOP] ESC détecté. Arrêt du script.")
        stop_event.set()

    # Toggle pause sur F8
    if key == keyboard.Key.f8:
        if pause_event.is_set():
            pause_event.clear()
            print("\n[RESUME] Reprise (F8).")
        else:
            pause_event.set()
            print("\n[PAUSE] Pause manuelle (F8).")

    
def start_hotkey_listener():
    listener = keyboard.Listener(on_press=on_key_press)
    listener.daemon = True
    listener.start()
    return listener

def countdown(seconds: int = 3):
    for i in range(seconds, 0, -1):
        print(f"Début dans {i}… (ESC pour STOP, F8 pour pause)")
        time.sleep(1)

def jittered(base: float, jitter: float) -> float:
    """Retourne base +/- jitter (uniforme) sans jamais descendre sous 0."""
    if jitter <= 0:
        return max(0.0, base)
    return max(0.0, base + random.uniform(-jitter, jitter))

def random_offset(px: int) -> tuple[int, int]:
    if px <= 0:
        return 0, 0
    return random.randint(-px, px), random.randint(-px, px)

def click_tile(center_x: int, center_y: int) -> bool:
    """
    Clique une tuile.
    Retourne True si un replant a été effectué (2e clic), False sinon.
    """

    if stop_event.is_set():
        return False
    
    wait_if_paused()

    dx, dy = random_offset(RANDOM_OFFSET_PX)
    x = center_x + dx
    y = center_y + dy

    # Clic 1 = HARVEST
    pyautogui.click(x, y)

    if stop_event.is_set():
        return False

    # Clic 2 = REPLANT (si activé)
    if DOUBLE_CLICK:
        interval = jittered(CLICK_DELAY, CLICK_DELAY_JITTER)
        sleep_interruptible(interval)  # IMPORTANT: pause/stop safe
        if stop_event.is_set():
            return False
        wait_if_paused()
        pyautogui.click(x, y)
        replanted = True
    else:
        replanted = False

    between = jittered(BETWEEN_TILES_DELAY, BETWEEN_TILES_JITTER)
    sleep_interruptible(between)

    return replanted

def print_stats():
    if not cycle_times:
        return
    window = cycle_times[-STATS_WINDOW:]
    avg = statistics.mean(window)
    mn = min(window)
    mx = max(window)
    print(f"[STATS] cycles={len(cycle_times)} | moyenne({len(window)})={avg:.2f}s | min={mn:.2f}s | max={mx:.2f}s")
    print(f"[COUNT] harvests={total_harvests} | replants={total_replants} | pelles={total_shovels}")
    if avg > COOLDOWN_SECONDS:
        print(f"[INFO] Moyenne > {COOLDOWN_SECONDS:.1f}s → baisse delays/jitter")
    else:
        print(f"[INFO] Moyenne < {COOLDOWN_SECONDS:.1f}s → cooldown respecté (attente résiduelle).")


def run_cycles():
    global total_harvests, total_replants, total_shovels, per_tile_harvests, run_start_time

    origin_x = GRID["origin_x"] + OFFSET["dx"]
    origin_y = GRID["origin_y"] + OFFSET["dy"]
    rows, cols = GRID["rows"], GRID["cols"]
    step_x, step_y = GRID["step_x"], GRID["step_y"]

    # "ready_at" par tuile : moment où la tuile est à nouveau cliquable
    ready_at = {(r, c): 0.0 for r in range(rows) for c in range(cols)}

    # init compteurs par tuile
    per_tile_harvests = {(r, c): 0 for r in range(rows) for c in range(cols)}

    run_start_time = time.monotonic()

    cycle = 0
    while not stop_event.is_set():
        wait_if_paused()

        cycle += 1
        print(f"\n=== Cycle {cycle} === (ESC stop / F8 pause)")

        t0 = time.monotonic()
        next_start = t0 + COOLDOWN_SECONDS

        for r in range(rows):
            for c in range(cols):
                if stop_event.is_set():
                    break

                wait_if_paused()

                # Attendre que cette tuile soit prête
                now = time.monotonic()
                wait = ready_at[(r, c)] - now
                if wait > 0:
                    sleep_interruptible(wait)
                    if stop_event.is_set():
                        break

                # Clique la tuile (1 harvest)
                x = origin_x + c * step_x
                y = origin_y + r * step_y
                replanted = click_tile(x, y)


                # --- Comptage ---
                total_harvests += 1
                per_tile_harvests[(r, c)] += 1

                if replanted:
                    total_replants += 1

                # Tous les 3 harvests sur cette tuile => 1 pelle + 1 replant
                tile_h = per_tile_harvests[(r, c)]
                if (tile_h - 1) % HARVESTS_PER_SHOVEL == 0:
                    total_shovels += 1
                    print(f"[SHOVEL] Tuile ({r},{c}) harvest #{tile_h} → +1 pelle (total={total_shovels})")

                # Check pause/stop auto après chaque tuile
                maybe_pause_or_stop()
                if stop_event.is_set():
                    break

                # Après le clic, la tuile redevient prête dans COOLDOWN_SECONDS
                ready_at[(r, c)] = time.monotonic() + COOLDOWN_SECONDS

            if stop_event.is_set():
                break

        elapsed = time.monotonic() - t0
        cycle_times.append(elapsed)

        print(f"Cycle en {elapsed:.2f}s")
        print_stats()

        if stop_event.is_set():
            break

        # Attendre jusqu'à la deadline (si on est en avance)
        remaining = next_start - time.monotonic()
        if remaining > 0:
            print(f"Attente cooldown: {remaining:.2f}s (départ cycle à t0+{COOLDOWN_SECONDS:.1f}s)")
            sleep_interruptible(remaining)
        else:
            print(f"> {COOLDOWN_SECONDS:.1f}s (retard de {-remaining:.2f}s), relance direct")


if __name__ == "__main__":
    print("Auto-clicker grille (OS-level).")
    print("Stop: ESC (ou souris dans un coin grâce à FAILSAFE, ou Ctrl+C dans le terminal).")
    print("Pause/Resume: F8.")
    print("Avant de commencer, ouvre ton jeu et place la caméra comme d’habitude.")
    start_hotkey_listener()
    countdown(4)
    try:
        run_cycles()
    except pyautogui.FailSafeException:
        print("\n[STOP] FailSafe déclenché (souris dans un coin). Arrêt propre.")
    except KeyboardInterrupt:
        print("\n[STOP] Ctrl+C détecté. Arrêt propre.")