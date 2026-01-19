import time
import pyautogui

pyautogui.FAILSAFE = True

def wait_point(label: str):
    print(f"\n➡️ Place la souris sur: {label}")
    input("Puis appuie sur Entrée (ou mets la souris dans un coin pour STOP)… ")
    x, y = pyautogui.position()
    print(f"   Capturé: x={x}, y={y}")
    return x, y

def main():
    print("=== Calibration grille ===")
    print("Failsafe: souris dans un coin pour arrêter.")
    print("Astuce: zoome/caméra fixe avant de mesurer.")
    time.sleep(1)

    # 1) Tuile haut-gauche (centre)
    x0, y0 = wait_point("le CENTRE de la tuile haut-gauche (0,0)")

    # 2) Tuile à droite (centre) -> calcule step_x
    x1, y1 = wait_point("le CENTRE de la tuile juste à DROITE (0,1)")

    # 3) Tuile en dessous (centre) -> calcule step_y
    x2, y2 = wait_point("le CENTRE de la tuile juste EN DESSOUS (1,0)")

    step_x = x1 - x0
    step_y = y2 - y0

    print("\n=== Résultat ===")
    print(f'origin_x = {x0}')
    print(f'origin_y = {y0}')
    print(f'step_x   = {step_x}')
    print(f'step_y   = {step_y}')

    print("\nCopie/colle ça dans ton script:")
    print(f'''
GRID = {{
  "origin_x": {x0},
  "origin_y": {y0},
  "step_x": {step_x},
  "step_y": {step_y},
  "rows": 5,   # à ajuster
  "cols": 4    # à ajuster
}}
''')

if __name__ == "__main__":
    main()
