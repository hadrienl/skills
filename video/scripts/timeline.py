"""Timeline d'un clip filmé : temps morts, coupes, placement des voix.

Partagé par montage_web.py (une vidéo par langue, textes incrustés) et package_player.py (une vidéo pour
toutes les langues, textes en HTML). Les voix sont données comme une liste de (t, durée), t en secondes du
CLIP SOURCE ; rien ici ne connaît le format du plan ni la langue.
"""
import re
import subprocess

FF, FP = "/usr/local/bin/ffmpeg", "/usr/local/bin/ffprobe"
FREEZE_MIN = 1.2      # un passage figé plus court n'est pas un temps mort
KEEP_BEFORE = 0.5     # pause gardée avant le geste qui suit un temps mort
KEEP_AFTER = 0.3      # … et juste avant qu'il commence
GAP = 0.25            # silence minimal entre deux voix
MERGE = 1.0           # deux passages figés séparés de moins d'1 s n'en font qu'un
# Rythme : un passage MUET (aucune voix) plus long que SILENT_MAX est raccourci même si l'écran bouge (frappe,
# réponse qui s'écrit, chargement animé) : on garde SILENT_HEAD après la voix et SILENT_TAIL avant la suivante.
# Retour d'usage (01/10) : des silences de 3 s et plus « cassent le rythme » ; on coupe plutôt qu'accélérer.
SILENT_MAX = 2.5
SILENT_HEAD = 0.6
SILENT_TAIL = 0.9


def probe(path, entry):
    return subprocess.run([FP, "-v", "error", "-show_entries", entry, "-of", "csv=p=0", path],
                          capture_output=True, text=True).stdout.strip()


def dur(path):
    return float(probe(path, "format=duration"))


def size(path):
    out = subprocess.run([FP, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
    w, h = out.splitlines()[0].split(",")
    return int(w), int(h)


_freezes = {}


def freezes(src):
    """Passages figés du clip [(a, b)], fusionnés quand ils se touchent presque."""
    if src not in _freezes:
        err = subprocess.run([FF, "-hide_banner", "-i", src, "-vf", f"freezedetect=n=0.00005:d={FREEZE_MIN}",
                              "-an", "-f", "null", "-"], capture_output=True, text=True).stderr
        v = [float(x) for x in re.findall(r"freeze_(?:start|end): ([0-9.]+)", err)]
        total, merged = dur(src), []
        for a, b in ((v[i], v[i + 1] if i + 1 < len(v) else total) for i in range(0, len(v), 2)):
            if merged and a - merged[-1][1] <= MERGE:
                merged[-1] = (merged[-1][0], b)
            else:
                merged.append((a, b))
        _freezes[src] = merged
    return _freezes[src]


def speech_windows(voices):
    """Fenêtres de parole en temps source : chaque voix attend la fin de la précédente."""
    out, end = [], -1.0
    for t, d in sorted(voices):
        start = max(t, end + GAP)
        end = start + d
        out.append((t, end + 0.3))
    return out


def auto_cuts(src, trim, voices):
    """Retire les temps morts de [trim] sans jamais couper une image pendant qu'une voix parle."""
    t0, t1 = trim
    busy, cuts = speech_windows(voices), []
    for a, b in freezes(src):
        a, b = max(a, t0), min(b, t1)
        ca, cb = a + KEEP_BEFORE, (b if b >= t1 - 0.1 else b - KEEP_AFTER)
        for ba, bb in busy:
            if ba < cb and bb > ca:
                if ba <= ca:
                    ca = max(ca, bb)
                else:
                    cb = min(cb, ba)
        if cb - ca > 0.6:
            cuts.append([round(ca, 2), round(cb, 2)])
    cuts += silent_cuts(trim, busy)
    return cuts


def silent_cuts(trim, busy):
    """Coupes dans les passages sans voix trop longs (cf. SILENT_MAX), qu'ils soient figés ou non."""
    t0, t1 = trim
    cuts, cursor = [], t0
    for ba, bb in sorted(busy) + [(t1 + SILENT_TAIL, t1 + SILENT_TAIL)]:
        a, b = max(cursor, t0), min(ba, t1 + SILENT_TAIL)
        last = ba > t1                                    # fin d'étape : on laisse voir le résultat
        head = 0.3 if cursor <= t0 else (1.0 if last else SILENT_HEAD)   # début : l'image vient d'apparaître
        if b - a > SILENT_MAX:
            ca, cb = a + head, b - SILENT_TAIL
            if cb - ca > 0.6:
                cuts.append([round(ca, 2), round(min(cb, t1), 2)])
        cursor = max(cursor, bb)
    return cuts


def keep_ranges(trim, cuts):
    """Plages gardées du clip : le trim moins les coupes (qui peuvent se chevaucher ou déborder du trim)."""
    out = [list(trim)]
    for ca, cb in sorted(cuts):
        a, b = out[-1]
        ca, cb = max(ca, a), min(cb, b)
        if cb <= ca:
            continue                                # coupe hors de la plage restante, ou déjà couverte
        out.pop()
        if ca > a:
            out.append([a, ca])
        out.append([cb, b])
    return [r for r in out if r[1] - r[0] > 1e-3]


def src_to_out(t, ranges):
    """Temps source → temps monté (un instant coupé tombe au début de la plage suivante)."""
    acc = 0.0
    for a, b in ranges:
        if t <= b:
            return acc + max(0.0, t - a)
        acc += b - a
    return acc


def place(voices, ranges):
    """Début monté de chaque voix [(t, d)], rendus DANS L'ORDRE DONNÉ (l'appelant trie par t) :
    jamais deux voix superposées. Ne pas retrier ici : à t égal, l'ordre de l'appelant fait foi."""
    placed, end = [], None
    for t, d in voices:
        at = src_to_out(t, ranges)
        if end is not None:
            at = max(at, end + GAP)
        placed.append(at)
        end = at + d
    return placed
