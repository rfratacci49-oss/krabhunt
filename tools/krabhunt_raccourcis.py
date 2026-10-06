"""Raccourcis clavier globaux pour le compteur KRABHUNT.

Compte les rencontres avec une touche, même quand le jeu ou l'émulateur est au premier plan :
le programme écoute le clavier et envoie chaque appui au site.

Installation (une seule fois) :   pip install keyboard
Lancement :                       python krabhunt_raccourcis.py
                                  (ou : python krabhunt_raccourcis.py mon_fichier.json)

La configuration se télécharge depuis le site : Compteur → ⌨ Raccourcis globaux.
Elle est lue dans krabhunt_raccourcis.json, à côté de ce script.
Ctrl+C dans la fenêtre du programme pour l'arrêter.
"""
import json
import os
import sys
import urllib.error
import urllib.request

try:
    import keyboard
except ImportError:
    sys.exit("Le module « keyboard » manque : installez-le avec   pip install keyboard")

ACTIONS = {"+": "plus", "-": "moins", "timer": "timer", "plus": "plus", "moins": "moins"}


def load_config(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            config = json.load(f)
    except FileNotFoundError:
        sys.exit(f"Fichier de configuration introuvable : {path}\n"
                 "Téléchargez-le depuis le site (Compteur → ⌨ Raccourcis globaux).")
    except ValueError as error:
        sys.exit(f"{path} : JSON invalide ({error})")
    for key in ("site", "cle", "raccourcis"):
        if key not in config:
            sys.exit(f"{path} : champ « {key} » manquant")
    return config


def call(config, hunt_id, action):
    """Envoie l'action au site ; renvoie l'état de la chasse (dict) ou lève une erreur lisible."""
    url = f"{config['site'].rstrip('/')}/api/{config['cle']}/chasse/{hunt_id}"
    request = urllib.request.Request(
        url, data=json.dumps({"action": action}).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise RuntimeError(f"chasse {hunt_id} introuvable ou clé invalide (régénérée sur le site ?)")
        raise RuntimeError(f"erreur du site ({error.code})")
    except urllib.error.URLError as error:
        raise RuntimeError(f"site injoignable ({error.reason})")


def describe(state):
    if state["mode"] == "timer":
        s = state["elapsed"]
        clock = f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
        return f"{state['species']} : ⏱ {clock} ({'en cours' if state['running'] else 'en pause'})"
    return f"{state['species']} : {state['count']:,}".replace(",", " ")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "krabhunt_raccourcis.json")
    config = load_config(path)
    beep = config.get("son", False) and sys.platform == "win32"
    if beep:
        import winsound

    count = 0
    for shortcut in config["raccourcis"]:
        key, hunt_id = shortcut.get("touche"), shortcut.get("chasse")
        action = ACTIONS.get(shortcut.get("action", "+"))
        if not key or not isinstance(hunt_id, int) or not action:
            print(f"Raccourci ignoré (touche, chasse ou action invalide) : {shortcut}")
            continue

        def pressed(hunt_id=hunt_id, action=action, key=key):
            try:
                state = call(config, hunt_id, action)
                print(f"[{key}] {describe(state)}")
                if beep:
                    winsound.Beep(1200 if action != "moins" else 600, 60)
            except RuntimeError as error:
                print(f"[{key}] ⚠ {error}")

        try:
            # suppress=False : la touche continue d'arriver au jeu
            keyboard.add_hotkey(key, pressed, suppress=False, trigger_on_release=False)
        except ValueError:
            print(f"Touche inconnue, ignorée : « {key} »")
            continue
        print(f"  {key:<14} → {action:<6} chasse n° {hunt_id}")
        count += 1

    if not count:
        sys.exit("Aucun raccourci valide dans la configuration.")
    print(f"\n{count} raccourci{'s' if count > 1 else ''} actif{'s' if count > 1 else ''}. "
          "Ctrl+C pour arrêter.\n")
    try:
        keyboard.wait()
    except KeyboardInterrupt:
        print("Arrêt.")


if __name__ == "__main__":
    main()
