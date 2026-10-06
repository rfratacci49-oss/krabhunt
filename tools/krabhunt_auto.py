"""Compteur automatique KRABHUNT : compte une rencontre quand une image de référence apparaît à l'écran.

Pensé pour les resets (ex. HGSS) : on mémorise une zone de l'écran au moment de la rencontre
(cadre nom + PV du Pokémon adverse), puis chaque fois que cette zone réapparaît, +1 sur la chasse.
Le compteur ne se réarme que quand la zone a disparu : une seule rencontre comptée par combat.

Installation (une seule fois) :   pip install mss opencv-python
Calibrer un profil :              python krabhunt_auto.py calibrer ho-oh
Lancer le comptage :              python krabhunt_auto.py lancer ho-oh
Essai sans rien envoyer :         python krabhunt_auto.py lancer ho-oh --essai
Profils existants :               python krabhunt_auto.py profils

L'adresse du site et la clé sont lues dans krabhunt_raccourcis.json (page Compteur → ⌨ Raccourcis
globaux du site), à côté de ce script. Les profils sont rangés dans le dossier profils/.
"""
import argparse
import ctypes
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

try:
    import cv2
    import mss
    import numpy as np
except ImportError:
    sys.exit("Modules manquants : installez-les avec   pip install mss opencv-python")

screen_capture = getattr(mss, "MSS", None) or mss.mss  # nouveau nom (mss ≥ 10), ancien en repli

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILES = os.path.join(HERE, "profils")
CONFIG = os.path.join(HERE, "krabhunt_raccourcis.json")
COMPARE_WIDTH = 160      # la zone est réduite à cette largeur avant comparaison (rapide, tolère le bruit)
KEEP_SNAPSHOTS = 50      # captures gardées par profil pour vérifier les détections
WINDOW = "KRABHUNT auto"

if sys.platform == "win32":
    # Coordonnées en pixels réels même avec une mise à l'échelle Windows (125 %, 150 %…)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass


# --- Site --------------------------------------------------------------------

def load_site():
    try:
        with open(CONFIG, encoding="utf-8-sig") as f:
            config = json.load(f)
        return config["site"].rstrip("/"), config["cle"]
    except FileNotFoundError:
        sys.exit(f"{CONFIG} introuvable : téléchargez-le depuis le site "
                 "(Compteur → ⌨ Raccourcis globaux) et placez-le à côté de ce script.")
    except (ValueError, KeyError):
        sys.exit(f"{CONFIG} : fichier invalide (champs « site » et « cle » attendus).")


def api(site, key, path, payload=None):
    request = urllib.request.Request(
        f"{site}/api/{key}/{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        method="POST" if payload is not None else "GET",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError("chasse introuvable ou clé invalide" if error.code == 404
                           else f"erreur du site ({error.code})")
    except urllib.error.URLError as error:
        raise RuntimeError(f"site injoignable ({error.reason})")


# --- Images ------------------------------------------------------------------

def grab(sct, region):
    """Capture d'une zone {left, top, width, height} en BGR."""
    return cv2.cvtColor(np.array(sct.grab(region)), cv2.COLOR_BGRA2BGR)


def prepare(image):
    """Version réduite, en niveaux de gris et légèrement floutée : insensible au bruit de capture."""
    h, w = image.shape[:2]
    small = cv2.resize(image, (COMPARE_WIDTH, max(1, round(h * COMPARE_WIDTH / w))),
                       interpolation=cv2.INTER_AREA)
    return cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (3, 3), 0)


def similarity(prepared, reference):
    """Ressemblance de 0 à 100 % (100 = identique)."""
    return 100.0 * (1.0 - float(np.mean(cv2.absdiff(prepared, reference))) / 255.0)


# --- Profils -----------------------------------------------------------------

def profile_paths(name):
    safe = "".join(c for c in name if c.isalnum() or c in "-_") or "profil"
    return os.path.join(PROFILES, f"{safe}.json"), os.path.join(PROFILES, f"{safe}.png"), safe


def load_profile(name):
    json_path, png_path, _ = profile_paths(name)
    try:
        with open(json_path, encoding="utf-8") as f:
            profile = json.load(f)
    except FileNotFoundError:
        sys.exit(f"Profil « {name} » introuvable. Créez-le avec :  python krabhunt_auto.py calibrer {name}")
    reference = cv2.imread(png_path)
    if reference is None:
        sys.exit(f"Image de référence manquante : {png_path}")
    return profile, reference


def choose_hunt(site, key):
    """Liste les chasses en cours du compte et demande laquelle compter."""
    try:
        hunts = api(site, key, "chasses")["chasses"]
    except RuntimeError as error:
        print(f"⚠ Impossible de lister les chasses ({error}).")
        hunts = []
    counting = [h for h in hunts if h["mode"] == "count"]
    if counting:
        print("\nChasses en cours (compteur de rencontres) :")
        for i, h in enumerate(counting, start=1):
            print(f"  {i}. {h['species']} · {h['game']} · {h['method']} ({h['count']} rencontres)")
        while True:
            answer = input("Numéro de la chasse à compter : ").strip()
            if answer.isdigit() and 1 <= int(answer) <= len(counting):
                return counting[int(answer) - 1]["id"]
    while True:
        answer = input("N° de la chasse (visible dans l'adresse /compteur/<n°>) : ").strip()
        if answer.isdigit():
            return int(answer)


def calibrate(name):
    site, key = load_site()
    json_path, png_path, safe = profile_paths(name)
    os.makedirs(PROFILES, exist_ok=True)

    with screen_capture() as sct:
        monitors = sct.monitors[1:]
        index = 1
        if len(monitors) > 1:
            print("Écrans :")
            for i, m in enumerate(monitors, start=1):
                print(f"  {i}. {m['width']}×{m['height']} (position {m['left']}, {m['top']})")
            answer = input("Écran où s'affiche le jeu [1] : ").strip()
            index = int(answer) if answer.isdigit() and 1 <= int(answer) <= len(monitors) else 1
        monitor = monitors[index - 1]

        input("\n1) Mettez le jeu sur l'écran de COMBAT (cadre nom + PV du Pokémon adverse visible),\n"
              "   puis appuyez sur Entrée ici… ")
        screen = grab(sct, monitor)

        # Sélection de la zone sur une version réduite de l'écran
        scale = min(1.0, 1400 / screen.shape[1], 850 / screen.shape[0])
        shown = cv2.resize(screen, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        print("2) Encadrez à la souris le cadre nom + PV de l'adversaire (une zone qui n'apparaît\n"
              "   QUE pendant la rencontre), puis Entrée. Échap pour annuler.")
        x, y, w, h = cv2.selectROI(WINDOW, shown, showCrosshair=False)
        cv2.destroyAllWindows()
        if w < 4 or h < 4:
            sys.exit("Zone trop petite ou sélection annulée.")
        region = {"left": monitor["left"] + round(x / scale), "top": monitor["top"] + round(y / scale),
                  "width": round(w / scale), "height": round(h / scale)}
        # Référence = la zone dans la capture prise pendant la rencontre
        top, left = region["top"] - monitor["top"], region["left"] - monitor["left"]
        reference = screen[top:top + region["height"], left:left + region["width"]].copy()

        hunt_id = choose_hunt(site, key)

        # Essai en direct pour régler le seuil
        print("\n3) Essai en direct : faites un reset complet et regardez le score.\n"
              "   Il doit dépasser le seuil pendant la rencontre et retomber nettement le reste du temps.\n"
              "   Réglez le seuil avec la barre, puis  S = enregistrer,  Échap = annuler.")
        ref_prepared = prepare(reference)
        threshold = [90]
        cv2.namedWindow(WINDOW)
        cv2.createTrackbar("Seuil %", WINDOW, threshold[0], 100, lambda v: threshold.__setitem__(0, v))
        best = low = None
        while True:
            live = grab(sct, region)
            score = similarity(prepare(live), ref_prepared)
            best = score if best is None else max(best, score)
            low = score if low is None else min(low, score)
            view = np.hstack([cv2.resize(reference, (live.shape[1], live.shape[0])), live])
            factor = max(1, 360 // max(1, view.shape[0]))
            view = cv2.resize(view, None, fx=factor, fy=factor, interpolation=cv2.INTER_NEAREST)
            hit = score >= threshold[0]
            bar = np.zeros((70, view.shape[1], 3), np.uint8)
            cv2.putText(bar, f"score {score:5.1f} %   seuil {threshold[0]} %   {'RENCONTRE' if hit else ''}",
                        (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 220, 120) if hit else (200, 200, 200), 2)
            cv2.putText(bar, f"min {low:5.1f}   max {best:5.1f}      gauche : reference  /  droite : en direct",
                        (8, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 160), 1)
            cv2.imshow(WINDOW, np.vstack([view, bar]))
            k = cv2.waitKey(100) & 0xFF
            if k in (ord("s"), ord("S")):
                break
            if k == 27:
                cv2.destroyAllWindows()
                sys.exit("Calibrage annulé.")
        cv2.destroyAllWindows()

    profile = {"nom": name, "region": region, "seuil": threshold[0], "chasse": hunt_id,
               "delai": 5, "rearmement": 10, "images_consecutives": 2, "images_absence": 8,
               "son": True, "touche_pause": "f8"}
    cv2.imwrite(png_path, reference)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    print(f"\nProfil enregistré : {json_path}\nLancez le comptage avec :  python krabhunt_auto.py lancer {safe}")


# --- Comptage ----------------------------------------------------------------

def run(name, dry_run=False, preview=False):
    profile, reference = load_profile(name)
    site, key = load_site()
    region, threshold = profile["region"], float(profile["seuil"])
    rearm_below = threshold - float(profile.get("rearmement", 10))
    min_delay = float(profile.get("delai", 5))
    needed = max(1, int(profile.get("images_consecutives", 2)))
    # La zone doit avoir disparu ~0,8 s avant de réarmer : une animation qui passe brièvement
    # sur le cadre pendant le combat ne compte pas une seconde rencontre
    absent_needed = max(1, int(profile.get("images_absence", 8)))
    hunt_id = profile["chasse"]
    _, _, safe = profile_paths(name)
    snapshots = os.path.join(PROFILES, f"{safe}_detections")
    os.makedirs(snapshots, exist_ok=True)

    beep = profile.get("son") and sys.platform == "win32"
    if beep:
        import winsound

    paused = [False]
    try:  # touche de pause facultative (module « keyboard » des raccourcis globaux)
        import keyboard
        pause_key = profile.get("touche_pause") or "f8"
        keyboard.add_hotkey(pause_key, lambda: (paused.__setitem__(0, not paused[0]),
                                                print("⏸ En pause" if paused[0] else "▶ Reprise")))
        pause_help = f"{pause_key} = pause / reprise, "
    except Exception:
        pause_help = ""

    print(f"Profil « {profile['nom']} » : chasse n° {hunt_id}, seuil {threshold:.0f} %, "
          f"zone {region['width']}×{region['height']} en ({region['left']}, {region['top']})")
    print(("MODE ESSAI : rien n'est envoyé au site. " if dry_run else "")
          + f"{pause_help}Ctrl+C pour arrêter.\n")

    ref_prepared = prepare(reference)
    armed, streak, absent, last_count, total = True, 0, 0, 0.0, 0
    with screen_capture() as sct:
        try:
            while True:
                started = time.perf_counter()
                live = grab(sct, region)
                score = similarity(prepare(live), ref_prepared)

                if not paused[0]:
                    streak = streak + 1 if score >= threshold else 0
                    absent = absent + 1 if score < rearm_below else 0
                    if armed and streak >= needed and time.time() - last_count >= min_delay:
                        armed, last_count, total = False, time.time(), total + 1
                        stamp = datetime.now().strftime("%H:%M:%S")
                        cv2.imwrite(os.path.join(snapshots, datetime.now().strftime("%Y%m%d-%H%M%S.png")), live)
                        _prune(snapshots)
                        if dry_run:
                            print(f"{stamp}  rencontre détectée (score {score:.1f} %)  [essai, total {total}]")
                        else:
                            try:
                                state = api(site, key, f"chasse/{hunt_id}", {"action": "plus"})
                                print(f"{stamp}  +1 → {state['species']} : {state['count']:,}".replace(",", " ")
                                      + f"   (score {score:.1f} %)")
                            except RuntimeError as error:
                                print(f"{stamp}  ⚠ rencontre détectée mais non envoyée : {error}")
                        if beep:
                            winsound.Beep(1200, 80)
                    elif not armed and absent >= absent_needed:
                        armed = True  # la zone a disparu : prêt pour la prochaine rencontre

                if preview:
                    view = cv2.resize(live, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
                    cv2.putText(view, f"{score:.0f}%", (5, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                (80, 220, 120) if score >= threshold else (200, 200, 200), 2)
                    cv2.imshow(WINDOW, view)
                    cv2.waitKey(1)
                # ~10 images par seconde
                time.sleep(max(0.0, 0.1 - (time.perf_counter() - started)))
        except KeyboardInterrupt:
            print(f"\nArrêt. {total} rencontre{'s' if total > 1 else ''} comptée{'s' if total > 1 else ''} "
                  f"pendant cette session. Captures des détections : {snapshots}")


def _prune(folder):
    files = sorted(f for f in os.listdir(folder) if f.endswith(".png"))
    for old in files[:-KEEP_SNAPSHOTS]:
        os.remove(os.path.join(folder, old))


def list_profiles():
    names = sorted(f[:-5] for f in os.listdir(PROFILES) if f.endswith(".json")) if os.path.isdir(PROFILES) else []
    print("\n".join(f"  {n}" for n in names) if names else "Aucun profil. Créez-en un avec :  "
          "python krabhunt_auto.py calibrer <nom>")


def main():
    parser = argparse.ArgumentParser(description="Compteur automatique KRABHUNT (détection à l'écran).")
    sub = parser.add_subparsers(dest="commande", required=True)
    p = sub.add_parser("calibrer", help="créer ou refaire un profil (zone, image de référence, seuil)")
    p.add_argument("profil")
    p = sub.add_parser("lancer", help="compter automatiquement avec un profil")
    p.add_argument("profil")
    p.add_argument("--essai", action="store_true", help="détecter sans rien envoyer au site")
    p.add_argument("--apercu", action="store_true", help="afficher la zone surveillée et son score")
    sub.add_parser("profils", help="lister les profils")
    args = parser.parse_args()
    if args.commande == "calibrer":
        calibrate(args.profil)
    elif args.commande == "lancer":
        run(args.profil, dry_run=args.essai, preview=args.apercu)
    else:
        list_profiles()


if __name__ == "__main__":
    main()
