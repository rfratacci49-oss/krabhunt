"""Durées de chasse (en secondes) : saisie « H:MM:SS » et affichage en français."""
import re

DURATION_RE = re.compile(r"(\d+):([0-5]?\d)(?::([0-5]?\d))?")
WORDS_RE = re.compile(r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*min)?\s*(?:(\d+)\s*s)?", re.IGNORECASE)


def parse_duration(text):
    """Secondes d'après « 2:30:00 », « 2:30 » (heures:minutes) ou « 2 h 30 min » ; None si invalide."""
    text = (text or "").strip()
    if match := DURATION_RE.fullmatch(text):
        hours, minutes, seconds = (int(v or 0) for v in match.groups())
        return hours * 3600 + minutes * 60 + seconds
    if text and (match := WORDS_RE.fullmatch(text)) and any(match.groups()):
        hours, minutes, seconds = (int(v or 0) for v in match.groups())
        return hours * 3600 + minutes * 60 + seconds
    return None


def clock(seconds):
    """« 2:05:09 » : valeur des champs de saisie et du chronomètre."""
    seconds = int(seconds or 0)
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def format_duration(seconds):
    """« 2 h 05 min », « 12 min 30 s », « 45 s »."""
    if seconds is None:
        return ""
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {secs:02d} s" if secs else f"{minutes} min"
    return f"{secs} s"
