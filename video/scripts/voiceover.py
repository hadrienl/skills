#!/usr/bin/env python3
"""Génère la narration d'un plan.json avec Voicebox (API locale http://127.0.0.1:17493).

  voiceover.py plan.json [--profile Me] [--language fr] [--force] [--engine qwen] [--instruct "..."]
                         [--tempo 1.12] [--takes 2] [--max-takes 4] [--seed 1234] [--no-qc]
  voiceover.py plan.json --make-ref vo/en/step_1_1.raw.wav,vo/en/step_2_1.raw.wav,… --profile Me --language en
  voiceover.py plan.json --language fr --redo 3_3,4_2           # refaire des prises jugées mauvaises à l'écoute
  voiceover.py plan.json --language en --candidates 8_4 [--n 6] # N prises à comparer → vo/en/candidats.html
  voiceover.py plan.json --language en --pick 8_4=3@1.04,3_3=1  # installer un candidat (@ = hauteur ×1,04)

Boucle d'écoute (OBLIGATOIRE avant le montage, cf. SKILL.md § 6 ter) : après chaque génération, ouvrir
vo/<langue>/ecoute.html (prises triées, pires en haut) et faire lister à l'utilisateur les prises qui ne sont
pas sa voix → --redo ; celles que la sélection n'arrive pas à réussir (phrases courtes) → --candidates puis
--pick ; une fois une langue validée sans référence, --make-ref avec ses bonnes prises.

Pour chaque étape portant un champ "voice" (texte), écrit vo/step_<n>.wav à côté du plan et
renseigne "voice_file" + "voice_duration" dans le plan. La couverture peut aussi avoir "voice".
Les "comments" d'une étape ({"t", "text"}, cf. montage_web.py) sont générés un par un :
vo/step_<n>_<k>.wav.
Plan MULTILINGUE (package_player.py : "langs": ["fr", "en"], textes {"fr": …, "en": …}) : chaque langue de
"langs" (ou seulement --language) est générée dans vo/<langue>/, et le résultat est rangé sous
"voices": {"<langue>": {"file", "duration", "text"}} de l'élément. Une génération bloquée (statut
« loading_model » sans activité, vu le 26/09) est annulée puis relancée automatiquement.

Sélection des prises (retour d'usage du 01/10 : « une génération sur deux ne ressemble pas du tout à ma voix »,
« certains passages soudain accélérés », « rythme mollasson ») :
- Le clonage (Qwen) part environ une fois sur deux sur un autre timbre. Chaque phrase est donc générée au moins
  --takes fois (seeds différentes) et au plus --max-takes ; on garde la prise dont le TIMBRE (spectre moyen à
  long terme, 24 bandes de 100 Hz à 7 kHz, normalisé) est le plus proche de la référence du profil dans cette
  langue, tant que son débit reste plausible. Seuil validé à l'oreille sur 23 prises anglaises : ≤ 4 dB = la
  bonne voix, ≥ 4,2 dB = une autre (seule exception : une prise de 2 s, trop courte pour être jugée).
- Référence : voices/<profil>.<langue>.json dans ce skill. On la construit avec --make-ref à partir de prises
  VALIDÉES À L'OREILLE dans la même langue (l'échantillon cloné est souvent dans une autre langue : le comparer à
  des phrases anglaises sépare mal). À défaut, l'échantillon du profil sert de référence provisoire.
- Ensuite chaque prise est rognée de ses silences et ramenée au MÊME débit, --tempo × débit de référence
  (atempo : hauteur inchangée). Brut gardé en step_*.raw.wav ; vo/<langue>/ecoute.html liste les prises triées
  par écart de timbre, à réécouter avant le montage.
"""
import argparse, array, cmath, hashlib, html, json, math, os, random, re, statistics, subprocess, sys, time, urllib.request

B = os.environ.get("VOICEBOX_URL", "http://127.0.0.1:17493")
FF = "/usr/local/bin/ffmpeg"
HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(os.path.dirname(HERE), "voices")
TIMBRE_MAX = 4.0     # dB : au-delà, ce n'est plus la voix du profil
RATE_TOL = 0.25      # débit toléré à ±25 % de la référence avant la mise au débit commun


def call(method, path, body=None, raw=False, timeout=60):
    req = urllib.request.Request(B + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if raw else json.loads(data or b"null")


def wait(gid, stall=90, limit=600):
    t0 = last_change = time.time(); last = None
    while time.time() - t0 < limit:
        h = call("GET", f"/history/{gid}")
        st = h["status"]
        if st == "completed": return h
        if st in ("failed", "error"): raise RuntimeError(h.get("error"))
        if st != last: last, last_change = st, time.time()
        if time.time() - last_change > stall:          # bloqué : annuler + relancer
            print(f"  génération bloquée en « {st} », relance", flush=True)
            call("POST", f"/generate/{gid}/cancel"); call("POST", f"/generate/{gid}/retry")
            last_change = time.time()
        time.sleep(2)
    raise TimeoutError(gid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan", nargs="?"); ap.add_argument("--profile", default="Me")
    ap.add_argument("--engine", default=None); ap.add_argument("--instruct", default=None)
    ap.add_argument("--language", default=None); ap.add_argument("--force", action="store_true")
    ap.add_argument("--tempo", type=float, default=1.12, help="débit commun = référence × tempo (1 = naturel)")
    ap.add_argument("--takes", type=int, default=2, help="prises minimum par phrase")
    ap.add_argument("--max-takes", type=int, default=4, help="prises maximum si aucune n'a le bon timbre")
    ap.add_argument("--seed", type=int, default=1234); ap.add_argument("--no-qc", action="store_true")
    ap.add_argument("--make-ref", default=None, help="prises validées (séparées par des virgules) → référence")
    ap.add_argument("--redo", default=None, help="clés à regénérer (ex. 3_3,4_2), avec --language")
    ap.add_argument("--candidates", default=None, help="clés pour lesquelles générer --n prises à comparer")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--pick", default=None, help="clé=numéro[@hauteur] des candidats retenus (ex. 8_4=3@1.04)")
    a = ap.parse_args()
    a.language_set = a.language is not None
    a.language = a.language or "fr"
    profiles = call("GET", "/profiles")
    prof = next((p for p in profiles if p["name"] == a.profile or p["id"] == a.profile), None)
    if not prof: sys.exit(f"profil {a.profile!r} introuvable : {[p['name'] for p in profiles]}")
    if a.make_ref:
        if not a.language_set: sys.exit("--make-ref : préciser --language (sinon la référence fr serait écrasée)")
        return make_ref(prof, a.language, [p for p in a.make_ref.split(",") if p], a.plan)
    if not a.plan: sys.exit("plan.json manquant")
    plan = json.load(open(a.plan)); base = os.path.dirname(os.path.abspath(a.plan))
    os.makedirs(os.path.join(base, "vo"), exist_ok=True)
    langs = plan.get("langs")
    multi = bool(langs)
    if (a.redo or a.candidates or a.pick) and not a.language_set and multi:
        sys.exit("--redo / --candidates / --pick : préciser --language")
    folder = os.path.join(base, "vo", a.language) if multi else os.path.join(base, "vo")
    if a.candidates:
        return candidates(plan, a, prof, base, folder, multi, a.candidates.split(","))
    for key in (a.redo.split(",") if a.redo else []):  # oublier la prise : generate la refera, avec sélection
        it, field = find(plan, multi, key)
        for f in (os.path.join(folder, f"step_{key}.wav"), raw_of(os.path.join(folder, f"step_{key}.wav"))):
            if os.path.exists(f): os.remove(f)
        if multi: it.get("voices", {}).pop(a.language, None)
        else: it.pop("voice_text_done", None)
    for spec in (a.pick.split(",") if a.pick else []):
        key, rest = spec.split("=")
        n, _, pitch = rest.partition("@")
        it, field = find(plan, multi, key)
        src = os.path.join(folder, "cand", f"{key}_{n}.raw.wav")
        dst = raw_of(os.path.join(folder, f"step_{key}.wav"))
        if pitch:                                        # un peu grave/aigu : hauteur seule, durée inchangée
            f = float(pitch)
            subprocess.run([FF, "-v", "error", "-y", "-i", src, "-af",
                            f"asetrate=24000*{f},aresample=24000,atempo={1 / f:.5f}", "-ar", "24000", dst], check=True)
        else:
            subprocess.run(["cp", src, dst], check=True)
        text, shown = say(it, field, a.language, multi)
        if multi: it.setdefault("voices", {})[a.language] = {"file": "", "duration": 0, "text": shown, "spoken": text}
        else: it["voice_text_done"] = text
        print(f"{a.language} {key}: candidat {n} retenu{' (hauteur ×' + pitch + ')' if pitch else ''}")
    if a.redo or a.pick:
        json.dump(plan, open(a.plan, "w"), ensure_ascii=False, indent=2)
    if langs:                                            # plan multilingue (package_player.py)
        for lang in ([a.language] if a.language_set else langs):
            generate(plan, a, prof, base, lang, multi=True)
    else:
        generate(plan, a, prof, base, a.language, multi=False)


def items_of(plan, multi):
    """Éléments à dire : couverture, intro d'étape ("voice") et commentaires ("comments")."""
    out = []
    cov = plan.get("cover") or {}
    if cov.get("voice"): out.append(("cover", cov, "voice"))
    for i, s in enumerate(plan["steps"]):
        if s.get("voice"): out.append((str(i + 1), s, "voice"))
        for k, c in enumerate(s.get("comments", [])):
            if not multi: c.setdefault("voice", c.get("text", ""))
            out.append((f"{i + 1}_{k + 1}", c, "voice" if not multi else ("voice" if "voice" in c else "text")))
    return out


def say(it, field, lang, multi):
    """(texte DIT, texte AFFICHÉ). Un commentaire peut porter "voice" (prononciation) en plus de "text"
    (sous-titre) : « le tchat » dit, « le chat » affiché. Langue absente de "voice" → on dit le sous-titre
    (sinon cette langue perdait silencieusement le commentaire)."""
    if not multi:
        return it[field], it[field]
    pick = lambda v: v.get(lang) if isinstance(v, dict) else v
    shown = pick(it.get("text")) if "text" in it else pick(it.get(field))
    spoken = pick(it.get("voice")) if "voice" in it else None
    return spoken or shown, shown or spoken


def find(plan, multi, key):
    """(élément, champ) d'une clé « cover », « <étape> » ou « <étape>_<commentaire> »."""
    for k, it, field in items_of(plan, multi):
        if k == key: return it, field
    sys.exit(f"clé {key!r} inconnue")


def candidates(plan, a, prof, base, folder, multi, keys):
    """--n prises par phrase, sans sélection, à départager à l'oreille (vo/<langue>/candidats.html)."""
    ref = load_ref(prof, a.language, folder)
    os.makedirs(os.path.join(folder, "cand"), exist_ok=True)
    rows = []
    for key in keys:
        it, field = find(plan, multi, key)
        text, _ = say(it, field, a.language, multi)
        cells = []
        for n in range(a.n):
            raw = os.path.join(folder, "cand", f"{key}_{n}.raw.wav")
            out = os.path.join(folder, "cand", f"{key}_{n}.wav")
            if os.path.exists(raw):                      # déjà là : connu, pour ne pas le regénérer en double
                _seen.setdefault(text, set()).add(hashlib.md5(open(raw, "rb").read()).hexdigest())
            else:
                synth(base_body(a, prof, text, a.language), random.randrange(1, 2 ** 31), raw)
            m = measure(raw, text)
            rate = ref.get("rate") or m["rate"]
            finish(raw, out, m, max(0.85, min(1.25, rate * a.tempo / m["rate"])) if m["rate"] else 1.0)
            cells.append((n, timbre(ref, raw), os.path.relpath(out, folder)))
            print(f"{a.language} {key} candidat {n}: timbre {cells[-1][1]:.1f} dB", flush=True)
        rows.append((key, text, cells))
    body = "".join(
        f'<tr><td colspan="{a.n}"><b>{k}</b> — {html.escape(t)}</td></tr><tr>' + "".join(
            f'<td>n° {n} · {d:.1f} dB<br><audio controls preload="none" src="{src}" style="width:160px"></audio></td>'
            for n, d, src in c) + "</tr>" for k, t, c in rows)
    open(os.path.join(folder, "candidats.html"), "w").write(
        f'<!doctype html><meta charset="utf-8"><title>Candidats {a.language}</title><style>body{{font:15px system-ui;'
        f'margin:24px}}td{{padding:6px}}</style><h2>Choisir une prise par phrase (puis --pick clé=n°)</h2>'
        f'<table>{body}</table>')
    print(f"→ {os.path.join(folder, 'candidats.html')}")


def generate(plan, a, prof, base, lang, multi):
    folder = os.path.join(base, "vo", lang) if multi else os.path.join(base, "vo")
    os.makedirs(folder, exist_ok=True)
    ref = load_ref(prof, lang, folder)
    chosen = []                                          # (clé, élément, texte, sortie, écart de timbre)
    for key, it, field in items_of(plan, multi):
        text, shown = say(it, field, lang, multi)        # traduction absente : on saute
        if not text: continue
        out = os.path.join(folder, f"step_{key}.wav")
        v = it.get("voices", {}).get(lang, {})
        done = (v.get("spoken", v.get("text")) if multi else it.get("voice_text_done"))
        if os.path.exists(raw_of(out)) and done == text and not a.force:
            print(f"{lang} {key}: déjà généré")
            chosen.append((key, it, text, out, timbre(ref, raw_of(out)), shown))
            continue
        t0 = time.time()
        d_t, n = pick(a, prof, text, lang, raw_of(out), ref)
        flag = "" if d_t <= TIMBRE_MAX else "  ⚠ timbre douteux, à réécouter"
        print(f"{lang} {key}: timbre {d_t:.1f} dB, {n} prise(s), {time.time() - t0:.0f} s{flag}", flush=True)
        # marque « généré » tout de suite : une reprise après interruption ne refait pas cette phrase
        if multi: it.setdefault("voices", {})[lang] = {"file": os.path.relpath(out, base), "duration": 0, "text": shown, "spoken": text}
        else: it.update(voice_text_done=text)
        json.dump(plan, open(a.plan, "w"), ensure_ascii=False, indent=2)
        chosen.append((key, it, text, out, d_t, shown))
    # Mise au débit commun, en fin de langue (refaite à chaque passage, à partir des .raw.wav). Sans référence
    # validée, le débit de base est la médiane réelle des prises : un débit par défaut ralentissait le français,
    # plus dense en lettres que l'anglais (02/10).
    ms = {out: measure(raw_of(out), text) for _, _, text, out, _, _ in chosen}
    rates = [m["rate"] for m in ms.values() if m["rate"]]
    base_rate = ref.get("rate") or (statistics.median(rates) if rates else 0)
    report = []
    for key, it, text, out, d_t, shown in chosen:
        m = ms[out]
        # au-delà de ×1,25, l'oreille entend une voix « soudain accélérée » (retour du 01/10)
        factor = max(0.85, min(1.25, base_rate * a.tempo / m["rate"])) if m["rate"] and base_rate else 1.0
        finish(raw_of(out), out, m, factor)
        d = round(duration(out), 2)
        rel = os.path.relpath(out, base)
        if multi: it.setdefault("voices", {})[lang] = {"file": rel, "duration": d, "text": shown, "spoken": text}
        else: it.update(voice_file=rel, voice_duration=d, voice_text_done=text)
        report.append((d_t, key, text, out))
    json.dump(plan, open(a.plan, "w"), ensure_ascii=False, indent=2)
    print(f"{lang} : {len(chosen)} phrases au débit {base_rate * a.tempo:.1f} lettres/s", flush=True)
    listen_page(folder, lang, report, ref)


def pick(a, prof, text, lang, dest, ref):
    """Génère des prises jusqu'à en avoir une au bon timbre (au moins --takes) ; garde la meilleure."""
    best, n = None, 0
    while n < a.max_takes:
        cand = dest + f".take{n}.wav"
        synth(base_body(a, prof, text, lang), a.seed + 97 * n, cand)
        n += 1
        m = measure(cand, text)
        d = timbre(ref, cand)
        if a.no_qc:
            best = (0.0, d, m, cand); break
        off = (abs(m["rate"] / ref["rate"] - 1) > RATE_TOL if ref.get("rate") else False) if m["rate"] else True
        score = d + (3 if off else 0)                    # débit aberrant : pénalisé, pas exclu
        if best is None or score < best[0]:
            if best: os.remove(best[3])
            best = (score, d, m, cand)
        else:
            os.remove(cand)
        if n >= a.takes and best[1] <= TIMBRE_MAX and best[0] < 3:
            break
    os.replace(best[3], dest)
    return best[1], n


def raw_of(out):
    return out[:-4] + ".raw.wav"


def base_body(a, prof, text, lang):
    body = {"profile_id": prof["id"], "text": text, "language": lang, "normalize": True, "max_chunk_chars": 2000}
    if a.engine: body["engine"] = a.engine
    if a.instruct: body["instruct"] = a.instruct
    return body


_seen = {}   # empreinte audio → seed, par texte


def synth(body, seed, path):
    """Une prise. Voicebox renvoie parfois la MÊME prise pour des seeds différentes (02/10 : seeds 5000, 5062 et
    5124 → trois fichiers identiques à l'octet) : on retire alors une seed aléatoire, 3 fois au plus."""
    seen = _seen.setdefault(body["text"], set())
    for attempt in range(4):
        g = call("POST", "/generate", {**body, "seed": seed})
        wait(g["id"])
        data = call("GET", f"/audio/{g['id']}", raw=True)
        h = hashlib.md5(data).hexdigest()
        if h not in seen:
            break
        print(f"  prise identique à une précédente (seed {seed}), nouvelle seed", flush=True)
        seed = random.randrange(1, 2 ** 31)
    seen.add(h)
    open(path, "wb").write(data)


# ---------------------------------------------------------------- mesures (Python pur : pas de numpy ici)
def pcm(path, sr):
    raw = subprocess.run([FF, "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return array.array("h", raw)


def duration(path):
    return len(pcm(path, 8000)) / 8000


def measure(path, text):
    """Débit (lettres/s de parole) et bornes de la parole (s)."""
    sr, hop = 8000, 160                                   # trames de 20 ms
    x = pcm(path, sr)
    rms = [(sum(v * v for v in x[i:i + hop]) / hop) ** 0.5 for i in range(0, len(x) - hop, hop)]
    if not rms or max(rms) == 0:
        return {"rate": 0.0, "start": 0.0, "end": 0.0}
    thr = max(rms) * 0.03                               # bas : une fin douce (« -tée ») reste de la parole
    on = [i for i, r in enumerate(rms) if r > thr]
    first, last = on[0], on[-1]
    speech = (last - first + 1) * hop / sr
    return {"rate": len(re.findall(r"\w", text)) / speech, "start": first * hop / sr, "end": (last + 1) * hop / sr}


def _fft(a):
    n = len(a)
    if n == 1: return a
    e, o = _fft(a[0::2]), _fft(a[1::2])
    t = [cmath.exp(-2j * math.pi * k / n) * o[k] for k in range(n // 2)]
    return [e[k] + t[k] for k in range(n // 2)] + [e[k] - t[k] for k in range(n // 2)]


_N, _SR = 512, 16000
_EDGES = [int(f * _N / _SR) for f in [100 * (70 ** (i / 24)) for i in range(25)]]   # 100 Hz → 7 kHz
_WIN = [0.5 - 0.5 * math.cos(2 * math.pi * i / (_N - 1)) for i in range(_N)]


def ltas(path):
    """Spectre moyen à long terme des passages parlés (24 bandes log, dB, centré) : l'empreinte du timbre."""
    x = pcm(path, _SR)
    rms = [(sum(v * v for v in x[i:i + _N:4]) / (_N / 4)) ** 0.5 for i in range(0, len(x) - _N, _N)]
    if not rms: return [0.0] * 24
    top, acc, n = max(rms), [0.0] * 24, 0
    for j, r in enumerate(rms):
        if r < top * 0.25: continue
        sp = [abs(c) ** 2 for c in _fft([x[j * _N + i] * _WIN[i] for i in range(_N)])[:_N // 2]]
        for b in range(24):
            lo, hi = _EDGES[b], max(_EDGES[b + 1], _EDGES[b] + 1)
            acc[b] += 10 * math.log10(sum(sp[lo:hi]) / (hi - lo) + 1e-9)
        n += 1
    v = [s / max(n, 1) for s in acc]; mu = sum(v) / 24
    return [s - mu for s in v]


def timbre(ref, path):
    return (sum((p - q) ** 2 for p, q in zip(ref["ltas"], ltas(path))) / 24) ** 0.5


def ref_path(prof, lang):
    return os.path.join(REFS, f"{re.sub(r'[^A-Za-z0-9_-]+', '_', prof['name'])}.{lang}.json")


def make_ref(prof, lang, takes, plan_path=None):
    """Référence = moyenne des timbres des prises validées ; débit = médiane de leurs débits (textes du plan)."""
    vs = [ltas(p) for p in takes]
    texts = {}
    if plan_path:
        plan = json.load(open(plan_path))
        for key, it, field in items_of(plan, bool(plan.get("langs"))):
            t, _ = say(it, field, lang, bool(plan.get("langs")))
            if t: texts[f"step_{key}"] = t
    rates = [measure(p, texts[k])["rate"] for p in takes
             if (k := os.path.basename(p).split(".")[0]) in texts]
    ref = {"profile": prof["name"], "language": lang, "takes": len(takes),
           "rate": round(statistics.median(rates), 2) if rates else None,
           "ltas": [round(statistics.mean(v[b] for v in vs), 3) for b in range(24)]}
    os.makedirs(REFS, exist_ok=True)
    json.dump(ref, open(ref_path(prof, lang), "w"), indent=1)
    print(f"référence {ref_path(prof, lang)} : {len(takes)} prises")


def load_json(p):
    try: return json.load(open(p))
    except (OSError, ValueError): return None


def load_ref(prof, lang, folder):
    ref = load_json(ref_path(prof, lang))
    if ref: return ref
    samples = call("GET", f"/profiles/{prof['id']}/samples") or []
    if not samples: sys.exit(f"profil {prof['name']} sans échantillon : faire --make-ref")
    path = os.path.join(folder, "profile_sample.wav")
    open(path, "wb").write(call("GET", f"/samples/{samples[0]['id']}", raw=True))
    print(f"⚠ pas de référence {lang} pour {prof['name']} : échantillon du profil en provisoire "
          f"(langue {prof.get('language')}). Valider des prises à l'oreille puis --make-ref.", flush=True)
    return {"ltas": ltas(path), "rate": None}


def finish(raw, out, m, factor):
    """Rogne les silences de bord puis ramène au débit commun, sans changer la hauteur. Marge de fin large :
    rogner au ras coupait les finales douces (« La capacité est ajoutée » amputée de « -tée », 02/10)."""
    a, b = max(0.0, m["start"] - 0.05), m["end"] + 0.25
    subprocess.run([FF, "-v", "error", "-y", "-i", raw, "-af",
                    f"atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,atempo={factor:.4f}", out], check=True)


def listen_page(folder, lang, report, ref):
    rows = "".join(
        f'<tr><td class="{"bad" if d > TIMBRE_MAX else ""}">{d:.1f} dB</td><td>{k}</td>'
        f'<td><audio controls preload="none" src="{os.path.basename(o)}"></audio></td><td>{html.escape(t)}</td></tr>'
        for d, k, t, o in sorted(report, key=lambda r: -r[0]))
    open(os.path.join(folder, "ecoute.html"), "w").write(
        f'<!doctype html><meta charset="utf-8"><title>Voix {lang}</title><style>body{{font:15px system-ui;margin:24px}}'
        f'td{{padding:6px 10px;border-bottom:1px solid #eee}}.bad{{color:#c00;font-weight:600}}</style>'
        f'<h2>Voix {lang} — écart de timbre à la référence (pires en haut)</h2><table>{rows}</table>')


if __name__ == "__main__":
    main()
