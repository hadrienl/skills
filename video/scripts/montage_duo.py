#!/usr/bin/env python3
"""Montage PAYSAGE 1920x1080 / 60 i/s : iOS et Android côte à côte, synchronisés par étape.

  montage_duo.py plan.json out.mp4

plan.json :
{
  "cover": {"eyebrow": "...", "title": "...", "sub": "...", "pill": "..."},
  "steps": [
    {"eyebrow": "Étape 1 / 8", "title": "Discuter", "sub": "...",
     "ios": "clips/ios_1.mp4", "android": "clips/and_1.mp4",
     "ios_note": "texte affiché à la place de l'écran iOS si \"ios\" est null"}
  ]
}
Chaque clip est filmé séparément, étape par étape, en commençant par ~3 s de pause sur l'état de
départ. Les deux clips d'une étape démarrent ensemble ; le plus court se fige sur sa dernière image
jusqu'à la fin du plus long (+1,5 s). Aucune accélération.
"""
import json, os, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FF, FP = "/usr/local/bin/ffmpeg", "/usr/local/bin/ffprobe"
TPL = os.environ.get("VIDEO_TEMPLATE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "template")  # dossier template (theme.json + fichiers)
TH = json.load(open(os.path.join(TPL, "theme.json"))); C = TH["colors"]
W, H, FPS, XF, CARD, TAIL = 1920, 1080, 60, 0.5, 3.0, 1.5
VO_DELAY, VO_TAIL, SR = 0.8, 1.0, 48000     # voix : démarre 0,8 s après le début de l'étape
PH_TOP, PH_H, RADIUS = 92, 880, 40
COLS = {"ios": 1085, "android": 1560}          # centre horizontal de chaque téléphone

def font(k, s):
    p = TH["fonts"][k]; f = ImageFont.truetype(p if os.path.isabs(p) else os.path.join(TPL, p), s)
    if k in ("title", "body_bold"):                         # police variable : graisse Bold
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
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw or not cur: cur = t
        else: out.append(cur); cur = w
    return out + ([cur] if cur else [])
def run(args): subprocess.run([FF, "-v", "error", "-y", *args], check=True)
def audio_args(item, L, idx):
    """Entrée audio de l'étape : narration décalée de VO_DELAY, ou silence, sur L secondes."""
    vf = item.get("voice_file")
    if vf:
        return ["-i", P(vf)], f"[{idx}:a]aresample={SR},aformat=channel_layouts=stereo,adelay={int(VO_DELAY*1000)}:all=1,apad,atrim=0:{L:.3f}[aud]"
    return ["-f", "lavfi", "-t", f"{L:.3f}", "-i", f"anullsrc=r={SR}:cl=stereo"], f"[{idx}:a]anull[aud]"
def voice_len(item): return VO_DELAY + item["voice_duration"] + VO_TAIL if item.get("voice_duration") else 0

def cover(c, path):
    im = Image.new("RGBA", (W, H), rgb(C["cover_bg"]))
    if asset("mark_light_blue"): im.alpha_composite(asset("mark_light_blue").resize((900, 900), Image.LANCZOS), (W - 820, 90))
    if asset("logo_white"): im.alpha_composite(fit(asset("logo_white"), 260), (110, 90))
    d = ImageDraw.Draw(im); y = 520
    d.text((110, y), c["eyebrow"].upper(), font=font("body_bold", 26), fill=rgb(C["cover_eyebrow"])); y += 52
    for line in wrap(d, c["title"], font("title", 104), 1000):
        d.text((110, y), line, font=font("title", 104), fill="white"); y += 116
    y += 14
    d.text((110, y), c["sub"], font=font("body", 34), fill=rgb(C["cover_subtitle"])); y += 90
    if c.get("pill"):
        f = font("body_bold", 28); tw = d.textlength(c["pill"], font=f)
        d.rounded_rectangle([110, y, 110 + tw + 80, y + 72], radius=12, fill="white")
        d.text((150, y + 36), c["pill"], font=f, fill=rgb(C["cover_pill_text"]), anchor="lm")
    im.convert("RGB").save(path)

def page(step, idx, all_steps, boxes, notes, path):
    im = Image.new("RGBA", (W, H), rgb(C["page_bg"]))
    d = ImageDraw.Draw(im)
    if asset("logo_color"): im.alpha_composite(fit(asset("logo_color"), 200), (90, 70))
    y = 190
    d.text((90, y), step["eyebrow"].upper(), font=font("body_bold", 24), fill=rgb(C["primary"])); y += 46
    for line in wrap(d, step["title"], font("title", 64), 640)[:3]:
        d.text((90, y), line, font=font("title", 64), fill=rgb(C["ink"])); y += 74
    y += 10
    for line in wrap(d, step["sub"], font("body", 28), 640)[:3]:
        d.text((90, y), line, font=font("body", 28), fill=rgb(C["muted"])); y += 38
    # sommaire : étape courante en bleu
    y = max(y + 50, 560)
    for i, s in enumerate(all_steps):
        cur = i == idx
        r = 17; cx, cy = 90 + r, y + r
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rgb(C["primary"]) if cur else rgb(C["border"]))
        d.text((cx, cy), str(i + 1), font=font("title", 20), fill="white" if cur else rgb(C["muted"]), anchor="mm")
        d.text((90 + 2 * r + 16, cy), s["title"], font=font("body_bold" if cur else "body", 24),
               fill=rgb(C["ink"]) if cur else rgb(C["muted"]), anchor="lm")
        y += 48
    d.text((90, H - 50), plan.get("footer", TH.get("labels", {}).get("footer_right", "CONFIDENTIEL · Usage interne Prisme.ai")), font=font("body", 20), fill=rgb(C["muted"]), anchor="lm")
    for plat, (x0, y0, x1, y1) in boxes.items():
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([x0, y0 + 12, x1, y1 + 12], radius=RADIUS + 4, fill=(21, 27, 36, 46))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(22)))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([x0 - 3, y0 - 3, x1 + 3, y1 + 3], radius=RADIUS + 3, fill=rgb(C["border"]))
        if plat in notes:                                 # pas d'écran : carte grise explicative
            d.rounded_rectangle([x0, y0, x1, y1], radius=RADIUS, fill=rgb(C["surface"]))
            ty = (y0 + y1) // 2 - 60
            for line in wrap(d, notes[plat], font("body", 26), x1 - x0 - 60):
                d.text(((x0 + x1) // 2, ty), line, font=font("body", 26), fill=rgb(C["muted"]), anchor="mm"); ty += 36
        label = plan.get("device_labels", {}).get(plat) or {"ios": "iOS · SwiftUI", "android": "Android · Jetpack Compose"}[plat]
        d.text(((x0 + x1) // 2, y1 + 38), label, font=font("body_bold", 22), fill=rgb(C["muted"]), anchor="mm")
    im.convert("RGB").save(path)

plan = json.load(open(sys.argv[1])); out = sys.argv[2]
base = os.path.dirname(os.path.abspath(sys.argv[1]))
tmp = tempfile.mkdtemp(prefix="pvduo-")
def P(p): return p if os.path.isabs(p) else os.path.join(base, p)

# géométrie des écrans d'après la 1ʳᵉ source de chaque plateforme
geo = {}
for plat in COLS:
    src = next((P(s[plat]) for s in plan["steps"] if s.get(plat)), None)
    sw, sh = size(src) if src else (1320, 2868)
    w = round(PH_H * sw / sh / 2) * 2; x0 = COLS[plat] - w // 2
    geo[plat] = (x0, PH_TOP, x0 + w, PH_TOP + PH_H)
    m = Image.new("L", (w, PH_H), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, PH_H - 1], radius=RADIUS, fill=255)
    m.save(os.path.join(tmp, f"mask_{plat}.png"))

clips = []
if plan.get("cover"):
    cp = os.path.join(tmp, "cover.png"); cover(plan["cover"], cp)
    c = os.path.join(tmp, "c_cover.mp4"); L = max(CARD, voice_len(plan["cover"]))
    ain, afc = audio_args(plan["cover"], L, 1)
    run(["-loop", "1", "-t", f"{L:.3f}", "-i", cp, *ain, "-filter_complex", f"[0:v]fps={FPS},format=yuv420p[out];{afc}",
         "-map", "[out]", "-map", "[aud]", "-t", f"{L:.3f}", "-c:v", "libx264", "-crf", "16", "-c:a", "aac", "-b:a", "192k", c])
    clips.append(c)
for i, st in enumerate(plan["steps"]):
    srcs = {p: P(st[p]) for p in COLS if st.get(p)}
    L = max(max(dur(s) for s in srcs.values()) + TAIL, voice_len(st))
    notes = {p: st.get(f"{p}_note", plan.get("unavailable", "Non disponible")) for p in COLS if p not in srcs}
    bg = os.path.join(tmp, f"page{i}.png"); page(st, i, plan["steps"], geo, notes, bg)
    inputs, fc, cur, n = ["-loop", "1", "-t", f"{L:.3f}", "-i", bg], [f"[0:v]fps={FPS},format=rgba[bg]"], "bg", 1
    for plat, s in srcs.items():
        x0, y0, x1, y1 = geo[plat]
        inputs += ["-i", s, "-loop", "1", "-t", f"{L:.3f}", "-i", os.path.join(tmp, f"mask_{plat}.png")]
        fc.append(f"[{n}:v]fps={FPS},tpad=stop_mode=clone:stop_duration={L:.3f},trim=0:{L:.3f},setpts=PTS-STARTPTS,"
                  f"scale={x1 - x0}:{y1 - y0},setsar=1,format=rgba[v{n}];[v{n}][{n + 1}:v]alphamerge[r{n}];"
                  f"[{cur}][r{n}]overlay={x0}:{y0}[o{n}]")
        cur = f"o{n}"; n += 2
    fc.append(f"[{cur}]format=yuv420p[out]")
    ain, afc = audio_args(st, L, n); inputs += ain; fc.append(afc)
    c = os.path.join(tmp, f"c_{i}.mp4")
    run([*inputs, "-filter_complex", ";".join(fc), "-map", "[out]", "-map", "[aud]", "-t", f"{L:.3f}", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", c])
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
print(out, round(dur(out), 1), "s")
