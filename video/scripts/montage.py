#!/usr/bin/env python3
"""Montage vertical 1080x1920 / 60 i/s à la charte du template (VIDEO_TEMPLATE, défaut : template/).

  montage.py --src rec.mp4 --out demo.mp4 \
             --card "Sur-titre|Titre|Sous-titre|Pastille" \
             --seg "0:23.5|Étape 1 / 2|Discuter avec l'agent|Modèle par défaut" \
             --seg "33.8:end|Étape 2 / 2|Changer de modèle|Mistral large, puis nouvelle question"

Couverture = diapositive « cover » du template (fond bleu, grand symbole, pastille blanche).
Étapes = diapositive « page » : sur-titre bleu en capitales, titre Play Bold, sous-titre gris,
logo couleur, pied de page ; l'écran filmé est posé dans une carte à bord #E4E7ED.
Les temps des --seg sont ceux de la vidéo CFR 60 i/s (créée d'abord à côté de --src, avec 3 s
d'image figée en fin). Aucune accélération : on coupe les temps morts.
"""
import argparse, json, os, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FF, FP = "/usr/local/bin/ffmpeg", "/usr/local/bin/ffprobe"
TPL = os.environ.get("VIDEO_TEMPLATE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "template")  # dossier template (theme.json + fichiers)
TH = json.load(open(os.path.join(TPL, "theme.json")))
C = TH["colors"]
W, H, FPS, XF, CARD = 1080, 1920, 60, 0.5, 2.8
SCREEN_TOP, SCREEN_BOTTOM, RADIUS = 330, 1770, 56

def font(key, size):
    p = TH["fonts"][key]
    f = ImageFont.truetype(p if os.path.isabs(p) else os.path.join(TPL, p), size)
    if key in ("title", "body_bold"):                     # police variable : graisse Bold
        try: f.set_variation_by_name("Bold")
        except Exception: pass
    return f
def asset(k):
    p = TH.get("assets", {}).get(k)
    return Image.open(os.path.join(TPL, p)).convert("RGBA") if p and os.path.exists(os.path.join(TPL, p)) else None
def rgb(h): return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
def dur(p): return float(subprocess.run([FP, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True).stdout)
def size(p):
    w, h = subprocess.run([FP, "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip().split(",")
    return int(w), int(h)
def fit(logo, w):
    return logo.resize((w, round(logo.height * w / logo.width)), Image.LANCZOS)
def wrap(draw, text, f, maxw):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if draw.textlength(t, font=f) <= maxw or not cur: cur = t
        else: lines.append(cur); cur = word
    return lines + ([cur] if cur else [])

def cover(eyebrow, title, sub, pill, path):
    im = Image.new("RGBA", (W, H), rgb(C["cover_bg"]))
    mark = asset("mark_light_blue")
    if mark: im.alpha_composite(mark.resize((860, 860), Image.LANCZOS), (W - 600, 230))                      # symbole débordant à droite, comme la diapo
    if asset("logo_white"): im.alpha_composite(fit(asset("logo_white"), 300), (80, 90))
    d = ImageDraw.Draw(im); y = 1140
    d.text((80, y), eyebrow.upper(), font=font("body_bold", 30), fill=rgb(C["cover_eyebrow"])); y += 60
    for line in wrap(d, title, font("title", 120), W - 160):
        d.text((80, y), line, font=font("title", 120), fill="white"); y += 132
    y += 20
    for line in wrap(d, sub, font("body", 38), W - 160):
        d.text((80, y), line, font=font("body", 38), fill=rgb(C["cover_subtitle"])); y += 52
    if pill:
        f = font("body_bold", 32); tw = d.textlength(pill, font=f); y += 50
        d.rounded_rectangle([80, y, 80 + tw + 90, y + 84], radius=14, fill=rgb(C["cover_pill_bg"]))
        d.text((80 + 45, y + 42), pill, font=f, fill=rgb(C["cover_pill_text"]), anchor="lm")
    d.text((80, H - 70), TH.get("labels", {}).get("footer_left", ""), font=font("body", 24), fill=rgb(C["cover_eyebrow"]))
    im.convert("RGB").save(path)

def page(eyebrow, title, sub, screen_box, path):
    im = Image.new("RGBA", (W, H), rgb(C["page_bg"]))
    d = ImageDraw.Draw(im)
    d.text((70, 78), eyebrow.upper(), font=font("body_bold", 30), fill=rgb(C["primary"]))
    logo = asset("logo_color")
    if logo: logo = fit(logo, 210); im.alpha_composite(logo, (W - 70 - logo.width, 66))
    y = 128
    for line in wrap(d, title, font("title", 72), W - 140)[:2]:
        d.text((70, y), line, font=font("title", 72), fill=rgb(C["ink"])); y += 84
    d.text((70, y + 6), sub, font=font("body", 34), fill=rgb(C["muted"]))
    # carte de l'écran : ombre douce + bord #E4E7ED
    x0, y0, x1, y1 = screen_box
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([x0, y0 + 14, x1, y1 + 14], radius=RADIUS + 4, fill=(21, 27, 36, 46))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(26)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], radius=RADIUS + 4, fill=rgb(C["border"]))
    d.line([(70, H - 96), (W - 70, H - 96)], fill=rgb(C["border"]), width=2)
    d.text((70, H - 58), TH.get("labels", {}).get("footer_left", ""), font=font("body", 24), fill=rgb(C["muted"]), anchor="lm")
    d.text((W - 70, H - 58), TH.get("labels", {}).get("footer_right", ""), font=font("body", 22), fill=rgb(C["muted"]), anchor="rm")
    im.convert("RGB").save(path)

ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--card", default=""); ap.add_argument("--seg", action="append", required=True)
a = ap.parse_args()
tmp = tempfile.mkdtemp(prefix="pv-")
cfr = os.path.splitext(a.src)[0] + "_cfr.mp4"
subprocess.run([FF, "-v", "error", "-y", "-i", a.src, "-vf", f"fps={FPS},tpad=stop_mode=clone:stop_duration=3",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p", cfr], check=True)
total = dur(cfr)
sw, sh_ = size(cfr); sh_px = SCREEN_BOTTOM - SCREEN_TOP; vw = round(sh_px * sw / sh_ / 2) * 2; x0 = (W - vw) // 2
box = (x0, SCREEN_TOP, x0 + vw, SCREEN_BOTTOM)
mask = os.path.join(tmp, "mask.png")
m = Image.new("L", (vw, sh_px), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, vw - 1, sh_px - 1], radius=RADIUS, fill=255); m.save(mask)

inputs, fc, outs, lens = [], [], [], []
n = 0
if a.card:
    eb, t, s, pill = (a.card.split("|") + ["", "", "", ""])[:4]
    cp = os.path.join(tmp, "cover.png"); cover(eb, t, s, pill, cp)
    inputs += ["-loop", "1", "-t", f"{CARD}", "-i", cp]
    fc.append(f"[{n}:v]fps={FPS},format=yuv420p,setsar=1[card]"); n += 1
    outs.append("card"); lens.append(CARD)
for k, spec in enumerate(a.seg):
    rng, eb, title, sub = (spec.split("|") + ["", "", ""])[:4]
    b, e = rng.split(":"); b = float(b); e = total if e == "end" else float(e)
    bg = os.path.join(tmp, f"page{k}.png"); page(eb, title, sub, box, bg)
    inputs += ["-ss", f"{b:.3f}", "-t", f"{e - b:.3f}", "-i", cfr,
               "-loop", "1", "-t", f"{e - b:.3f}", "-i", mask,
               "-loop", "1", "-t", f"{e - b:.3f}", "-i", bg]
    v, mk, pg = n, n + 1, n + 2; n += 3
    fc.append(f"[{v}:v]setpts=PTS-STARTPTS,scale={vw}:{sh_px},setsar=1,format=rgba[v{k}];[v{k}][{mk}:v]alphamerge[r{k}];"
              f"[{pg}:v]fps={FPS},format=rgba[p{k}];[p{k}][r{k}]overlay={x0}:{SCREEN_TOP}:shortest=1,format=yuv420p,setsar=1[s{k}]")
    outs.append(f"s{k}"); lens.append(e - b)
cur, acc = outs[0], lens[0]
for i in range(1, len(outs)):
    off = acc - XF
    fc.append(f"[{cur}][{outs[i]}]xfade=transition=fade:duration={XF}:offset={off:.3f}[x{i}]")
    cur, acc = f"x{i}", off + lens[i]
subprocess.run([FF, "-v", "error", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", f"[{cur}]", "-r", str(FPS),
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", a.out], check=True)
print(a.out, round(dur(a.out), 1), "s")
