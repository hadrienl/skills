#!/usr/bin/env python3
"""Montage PAYSAGE 1920x1080 / 60 i/s pour une démo WEB (Chrome piloté par web.mjs).

  montage_web.py plan.json out.mp4

plan.json (même format que montage_duo.py, clé "web" au lieu de "ios"/"android") :
{
  "cover": {"eyebrow": "...", "title": "...", "sub": "...", "pill": "...", "voice": "..."},
  "footer": "pied de page (optionnel)",
  "steps": [
    {"section": "Usage par chat", "eyebrow": "Étape 1 / 6", "title": "...", "sub": "...",
     "web": "clips/web_1.mp4", "url": "app.exemple.com/…", "trim": [2.0, 31.5], "voice": "..."}
  ]
}
- "section" (facultatif) : le sommaire liste les sections, pas les étapes — utile au-delà de 8 étapes.
- "url" (facultatif) : texte de la barre d'adresse dessinée au-dessus de l'écran.
- "trim" (facultatif) : [début, fin] en secondes dans le clip ; "cuts" : [[a, b], …] passages à retirer
  (attente du modèle, chargement figé) — on coupe, on n'accélère jamais.
- "cuts": "auto" : les passages figés (freezedetect, > 1,2 s) sont retirés en gardant ~0,5 s de pause avant
  chaque geste — mais jamais pendant qu'un commentaire parle (voir ci-dessous).
Voix : voiceover.py plan.json renseigne voice_file/voice_duration, lus ici comme dans montage_duo.py.
- "voice" (une phrase, au début de l'étape), et/ou
- "comments": [{"t": 12.4, "text": "Je clique sur Se connecter."}, …] : commentaires au fil de l'action,
  "t" en secondes DU CLIP SOURCE (repères de `web.mjs mark`). Placés au temps monté correspondant, jamais
  superposés (un commentaire attend la fin du précédent) ; l'étape s'allonge sur sa dernière image si besoin.
"""
import json, os, subprocess, sys, tempfile
import timeline
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FF, FP = "/usr/local/bin/ffmpeg", "/usr/local/bin/ffprobe"
TPL = os.environ.get("VIDEO_TEMPLATE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "template")
TH = json.load(open(os.path.join(TPL, "theme.json"))); C = TH["colors"]
W, H, FPS, XF, CARD, TAIL = 1920, 1080, 60, 0.5, 3.0, 1.2
VO_DELAY, VO_TAIL, SR = 0.8, 1.0, 48000
SIDE = 470                                       # colonne de texte à gauche
BOX = (SIDE + 20, 70, W - 60, H - 70)            # zone disponible pour la fenêtre
BAR, RADIUS = 40, 16                             # barre de navigateur dessinée, arrondi de la fenêtre

def font(k, s):
    p = TH["fonts"][k]; f = ImageFont.truetype(p if os.path.isabs(p) else os.path.join(TPL, p), s)
    if k in ("title", "body_bold"):
        try: f.set_variation_by_name("Bold")
        except Exception: pass
    return f
def asset(k):
    p = TH.get("assets", {}).get(k)
    return Image.open(os.path.join(TPL, p)).convert("RGBA") if p and os.path.exists(os.path.join(TPL, p)) else None
def rgb(h): return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
def fit(im, w): return im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
def dur(p): return float(subprocess.run([FP, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True).stdout)
def size(p):
    w, h = subprocess.run([FP, "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip().split(",")
    return int(w), int(h)
def wrap(d, text, f, maxw):
    out, cur = [], ""
    for w in (text or "").split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw or not cur: cur = t
        else: out.append(cur); cur = w
    return out + ([cur] if cur else [])
def run(args): subprocess.run([FF, "-v", "error", "-y", *args], check=True)
def audio_args(item, L, idx):
    vf = item.get("voice_file")
    if vf:
        return ["-i", P(vf)], f"[{idx}:a]aresample={SR},aformat=channel_layouts=stereo,adelay={int(VO_DELAY*1000)}:all=1,apad,atrim=0:{L:.3f}[aud]"
    return ["-f", "lavfi", "-t", f"{L:.3f}", "-i", f"anullsrc=r={SR}:cl=stereo"], f"[{idx}:a]anull[aud]"
def voice_len(item): return VO_DELAY + item["voice_duration"] + VO_TAIL if item.get("voice_duration") else 0

def comments(st):
    """Voix de l'étape en temps SOURCE : l'intro "voice" au début du trim, puis les "comments"."""
    t0 = st.get("trim", [0, 0])[0]
    out = [(t0 + VO_DELAY, st)] if st.get("voice_file") else []
    out += [(c["t"], c) for c in st.get("comments", []) if c.get("voice_file")]
    return sorted(out, key=lambda x: x[0])
def step_audio(st, ranges, body, idx):
    """Entrées + filtre audio : chaque voix posée à son temps monté, sans chevauchement (timeline.place)."""
    vs = comments(st)
    placed = list(zip(timeline.place([(t, c["voice_duration"]) for t, c in vs], ranges), (c for _, c in vs)))
    end = max((at + c["voice_duration"] for at, c in placed), default=0)
    L = max(body + TAIL, end + VO_TAIL)
    TIMELINE.append([(at, at + c["voice_duration"], c.get("text") or c.get("voice", "")) for at, c in placed])
    if not placed:
        return ["-f", "lavfi", "-t", f"{L:.3f}", "-i", f"anullsrc=r={SR}:cl=stereo"], f"[{idx}:a]anull[aud]", L
    ins, fc = [], []
    for k, (at, c) in enumerate(placed):
        ins += ["-i", P(c["voice_file"])]
        fc.append(f"[{idx + k}:a]aresample={SR},aformat=channel_layouts=stereo,adelay={int(at * 1000)}:all=1[vo{k}]")
    fc.append("".join(f"[vo{k}]" for k in range(len(placed))) + f"amix=inputs={len(placed)}:normalize=0:duration=longest,apad,atrim=0:{L:.3f}[aud]")
    return ins, ";".join(fc), L

def cover(c, path):
    im = Image.new("RGBA", (W, H), rgb(C["cover_bg"]))
    if asset("mark_light_blue"): im.alpha_composite(asset("mark_light_blue").resize((900, 900), Image.LANCZOS), (W - 820, 90))
    if asset("logo_white"): im.alpha_composite(fit(asset("logo_white"), 260), (110, 90))
    d = ImageDraw.Draw(im); y = 520
    d.text((110, y), c["eyebrow"].upper(), font=font("body_bold", 26), fill=rgb(C["cover_eyebrow"])); y += 52
    for line in wrap(d, c["title"], font("title", 104), 1000):
        d.text((110, y), line, font=font("title", 104), fill="white"); y += 116
    y += 14
    d.text((110, y), c.get("sub", ""), font=font("body", 34), fill=rgb(C["cover_subtitle"])); y += 90
    if c.get("pill"):
        f = font("body_bold", 28); tw = d.textlength(c["pill"], font=f)
        d.rounded_rectangle([110, y, 110 + tw + 80, y + 72], radius=12, fill=rgb(C["cover_pill_bg"]))
        d.text((150, y + 36), c["pill"], font=f, fill=rgb(C["cover_pill_text"]), anchor="lm")
    im.convert("RGB").save(path)

def geometry(src):
    """Fenêtre (barre + écran) la plus grande possible dans BOX, au ratio du clip."""
    sw, sh = size(src)
    bw, bh = BOX[2] - BOX[0], BOX[3] - BOX[1] - BAR
    w = min(bw, bh * sw / sh); w = int(w) // 2 * 2; h = int(w * sh / sw) // 2 * 2
    x0 = BOX[0] + (bw - w) // 2; y0 = BOX[1] + (BOX[3] - BOX[1] - h - BAR) // 2
    return x0, y0, w, h                       # (x0, y0) = coin haut-gauche de la barre

def page(step, idx, steps, geo, path):
    im = Image.new("RGBA", (W, H), rgb(C["page_bg"]))
    d = ImageDraw.Draw(im)
    if asset("logo_color"): im.alpha_composite(fit(asset("logo_color"), 190), (70, 66))
    y = 180
    d.text((70, y), step.get("eyebrow", "").upper(), font=font("body_bold", 22), fill=rgb(C["primary"])); y += 42
    for line in wrap(d, step["title"], font("title", 52), SIDE - 100)[:4]:
        d.text((70, y), line, font=font("title", 52), fill=rgb(C["ink"])); y += 60
    y += 12
    for line in wrap(d, step.get("sub", ""), font("body", 24), SIDE - 100)[:5]:
        d.text((70, y), line, font=font("body", 24), fill=rgb(C["muted"])); y += 33
    # sommaire : sections si présentes, sinon étapes ; l'élément courant en bleu
    if any(s.get("section") for s in steps):
        items = list(dict.fromkeys(s.get("section") for s in steps if s.get("section")))
        cur = step.get("section")
    else:
        items = [s["title"] for s in steps]; cur = step["title"]
    y = max(y + 44, 560); r = 15
    for i, it in enumerate(items):
        on = it == cur; cx, cy = 70 + r, y + r
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rgb(C["primary"]) if on else rgb(C["border"]))
        d.text((cx, cy), str(i + 1), font=font("title", 18), fill="white" if on else rgb(C["muted"]), anchor="mm")
        d.text((70 + 2 * r + 14, cy), wrap(d, it, font("body", 22), SIDE - 140)[0], font=font("body_bold" if on else "body", 22),
               fill=rgb(C["ink"]) if on else rgb(C["muted"]), anchor="lm")
        y += 42
        if y > H - 110: break
    d.text((70, H - 48), plan.get("footer", TH.get("labels", {}).get("footer_right", "")), font=font("body", 18), fill=rgb(C["muted"]), anchor="lm")
    # fenêtre : ombre, bord, barre de navigateur (3 pastilles + adresse)
    x0, y0, w, h = geo; x1, y1 = x0 + w, y0 + BAR + h
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([x0, y0 + 14, x1, y1 + 14], radius=RADIUS + 4, fill=(21, 27, 36, 50))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(24)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([x0 - 2, y0 - 2, x1 + 2, y1 + 2], radius=RADIUS + 2, fill=rgb(C["border"]))
    d.rounded_rectangle([x0, y0, x1, y0 + BAR + RADIUS], radius=RADIUS, fill=rgb(C["surface"]))
    for k, col in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
        cx = x0 + 24 + k * 22; d.ellipse([cx - 6, y0 + BAR // 2 - 6, cx + 6, y0 + BAR // 2 + 6], fill=col)
    if step.get("url"):
        ux0, ux1 = x0 + 110, x1 - 110
        d.rounded_rectangle([ux0, y0 + 8, ux1, y0 + BAR - 8], radius=(BAR - 16) // 2, fill="white", outline=rgb(C["border"]))
        d.text(((ux0 + ux1) // 2, y0 + BAR // 2), step["url"], font=font("body", 17), fill=rgb(C["muted"]), anchor="mm")
    im.convert("RGB").save(path)

plan = json.load(open(sys.argv[1])); out = sys.argv[2]
base = os.path.dirname(os.path.abspath(sys.argv[1]))
tmp = tempfile.mkdtemp(prefix="pvweb-")
def P(p): return p if os.path.isabs(p) else os.path.join(base, p)

first = next(P(s["web"]) for s in plan["steps"] if s.get("web"))
geo = geometry(first); x0, y0, w, h = geo
mask = os.path.join(tmp, "mask.png")                  # coins bas arrondis seulement (la barre couvre le haut)
m = Image.new("L", (w, h), 255); md = ImageDraw.Draw(m)
md.rectangle([0, h - RADIUS, w, h], fill=0); md.rounded_rectangle([0, h - 2 * RADIUS, w - 1, h - 1], radius=RADIUS, fill=255); m.save(mask)

clips, TIMELINE = [], []                             # TIMELINE : voix placées, par clip (temps local)
if plan.get("cover"):
    cp = os.path.join(tmp, "cover.png"); cover(plan["cover"], cp)
    c = os.path.join(tmp, "c_cover.mp4"); L = max(CARD, voice_len(plan["cover"]))
    TIMELINE.append([(VO_DELAY, VO_DELAY + plan["cover"]["voice_duration"], plan["cover"]["voice"])] if plan["cover"].get("voice_duration") else [])
    ain, afc = audio_args(plan["cover"], L, 1)
    run(["-loop", "1", "-t", f"{L:.3f}", "-i", cp, *ain, "-filter_complex", f"[0:v]fps={FPS},format=yuv420p[out];{afc}",
         "-map", "[out]", "-map", "[aud]", "-t", f"{L:.3f}", "-c:v", "libx264", "-crf", "16", "-c:a", "aac", "-b:a", "192k", c])
    clips.append(c)
for i, st in enumerate(plan["steps"]):
    src = P(st["web"])
    trim = [st.get("trim", [0, dur(src)])[0], min(st.get("trim", [0, dur(src)])[1], dur(src))]
    cuts = st.get("cuts", [])
    if cuts == "auto": cuts = timeline.auto_cuts(src, trim, [(t, c["voice_duration"]) for t, c in comments(st)])
    ranges = timeline.keep_ranges(trim, cuts)
    body = sum(b - a for a, b in ranges)
    ain, afc, L = step_audio(st, ranges, body, 3)
    bg = os.path.join(tmp, f"page{i}.png"); page(st, i, plan["steps"], geo, bg)
    n = len(ranges)
    fc = (f"[0:v]fps={FPS},format=rgba[bg];[1:v]fps={FPS},split={n}" + "".join(f"[s{k}]" for k in range(n)) + ";" +
          "".join(f"[s{k}]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS[t{k}];" for k, (a, b) in enumerate(ranges)) +
          "".join(f"[t{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0[cut];"
          f"[cut]tpad=stop_mode=clone:stop_duration={L:.3f},trim=0:{L:.3f},setpts=PTS-STARTPTS,scale={w}:{h}:flags=lanczos,setsar=1,format=rgba[v];"
          f"[v][2:v]alphamerge[r];[bg][r]overlay={x0}:{y0 + BAR},format=yuv420p[out]")
    inputs = ["-loop", "1", "-t", f"{L:.3f}", "-i", bg, "-i", src, "-loop", "1", "-t", f"{L:.3f}", "-i", mask] + ain
    c = os.path.join(tmp, f"c_{i}.mp4")
    run([*inputs, "-filter_complex", fc + ";" + afc, "-map", "[out]", "-map", "[aud]", "-t", f"{L:.3f}", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", c])
    clips.append(c); print(f"étape {i + 1} : {L:.1f} s", flush=True)
ds = [dur(c) for c in clips]
inputs = sum((["-i", c] for c in clips), []); fc, cur, acur, acc = [], "0:v", "0:a", ds[0]
for i in range(1, len(clips)):
    off = acc - XF
    fc.append(f"[{cur}][{i}:v]xfade=transition=fade:duration={XF}:offset={off:.3f}[x{i}]")
    fc.append(f"[{acur}][{i}:a]acrossfade=d={XF}[y{i}]")
    cur, acur, acc = f"x{i}", f"y{i}", off + ds[i]
run([*inputs, "-filter_complex", ";".join(fc) or "[0:v]null[x0];[0:a]anull[y0]", "-map", f"[{cur if fc else 'x0'}]",
     "-map", f"[{acur if fc else 'y0'}]", "-r", str(FPS),
     "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
# <out>.timeline.json : chaque voix avec son début/fin dans la vidéo finale (fondus déduits) → sous-titres
starts, acc = [0.0], ds[0]
for i in range(1, len(clips)): starts.append(acc - XF); acc = acc - XF + ds[i]
json.dump([{"start": round(starts[i] + a, 3), "end": round(starts[i] + b, 3), "text": t}
           for i, cl in enumerate(TIMELINE) for a, b, t in cl], open(os.path.splitext(out)[0] + ".timeline.json", "w"), ensure_ascii=False, indent=1)
print(out, round(dur(out), 1), "s")
