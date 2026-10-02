#!/usr/bin/env python3
"""Fabrique un template vidéo (theme.json + logos + polices) à partir d'une source de charte.

  extract_template.py SOURCE [SOURCE…] --out DOSSIER [--name "Marque"]

Sources reconnues (combinables : la première qui fournit un élément gagne) :
  .pptx .potx .ppsx      couleurs du thème + couleurs réellement utilisées, polices, images (logos), fond de couverture
  .key                   exporté en PDF via Keynote, puis traité comme un PDF
  .pdf                   1re page rendue en image (qlmanage) → palette ; texte → pas de polices fiables
  .png .jpg .jpeg .webp  palette dominante (capture d'écran, moodboard, charte) ; image à fond transparent = logo
  .svg                   logo (rendu en PNG via qlmanage)
  .css .scss             variables --x: #hex et font-family
  .json                  tokens {colors:{…}, fonts:{…}} ou theme.json déjà au bon format
  .ttf .otf              police (1re = titres, 2e = texte)
Écrit DOSSIER/theme.json (même schéma que prisme-video/template), les fichiers utiles et preview.png.
"""
import argparse, colorsys, glob, json, os, re, shutil, subprocess, sys, tempfile, zipfile
from collections import Counter
from PIL import Image

SYS_FONT_DIRS = ["/System/Library/Fonts", "/System/Library/Fonts/Supplemental", "/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
FALLBACK = {"title": "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "title_regular": "/System/Library/Fonts/Supplemental/Arial.ttf",
            "body": "/System/Library/Fonts/Supplemental/Arial.ttf", "body_bold": "/System/Library/Fonts/Supplemental/Arial Bold.ttf"}

def hx(rgb): return "#%02X%02X%02X" % tuple(int(v) for v in rgb[:3])
def rgb(h): h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
def lum(h):
    r, g, b = [v / 255 for v in rgb(h)]
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
def sat(h): return colorsys.rgb_to_hls(*[v / 255 for v in rgb(h)])[2]
def mix(a, b, t): return hx([x + (y - x) * t for x, y in zip(rgb(a), rgb(b))])
def contrast(a, b): la, lb = sorted([lum(a), lum(b)], reverse=True); return (la + .05) / (lb + .05)
def is_grey(h): c = rgb(h); return max(c) - min(c) < 30

class Acc:
    def __init__(s): s.colors = Counter(); s.theme = {}; s.fonts = []; s.font_files = []; s.logos = []; s.cover_bg = None; s.notes = []
A = Acc()

def find_font(name, bold=False):
    """Fichier de police installé pour un nom de famille (ex. « Play »), sinon Google Fonts, sinon None."""
    if not name: return None
    key = name.lower().replace(" ", "")
    cands = [f for d in SYS_FONT_DIRS for f in glob.glob(os.path.join(d, "*")) if os.path.basename(f).lower().replace(" ", "").startswith(key)]
    cands = [f for f in cands if f.lower().endswith((".ttf", ".otf", ".ttc")) and "italic" not in f.lower()]
    exact = [f for f in cands if os.path.splitext(os.path.basename(f))[0].lower().replace(" ", "") in (key + ("bold" if bold else ""), key + ("-bold" if bold else "-regular"))]
    if exact: return exact[0]
    want = [f for f in cands if ("bold" in f.lower()) == bold]
    if want: return sorted(want, key=len)[0]
    if cands: return sorted(cands, key=len)[0]
    return None

def google_font(name, out, bold):
    """Télécharge la police depuis github.com/google/fonts (statique si possible, sinon variable)."""
    d = name.lower().replace(" ", "")
    for lic in ("ofl", "apache", "ufl"):
        r = subprocess.run(["curl", "-sfL", f"https://api.github.com/repos/google/fonts/contents/{lic}/{d}"], capture_output=True, text=True)
        if r.returncode or not r.stdout.strip().startswith("["): continue
        files = [f for f in json.loads(r.stdout) if f["name"].endswith(".ttf") and "Italic" not in f["name"]]
        if not files: continue
        want = ["-Bold.ttf", "-SemiBold.ttf", "-Black.ttf"] if bold else ["-Regular.ttf", "-Medium.ttf"]
        pick = next((f for w in want for f in files if f["name"].endswith(w)), None) or next((f for f in files if "[" in f["name"]), files[0])
        dst = os.path.join(out, "fonts", pick["name"].replace("[", "-").replace("]", "").replace(",", "-"))
        if subprocess.run(["curl", "-sfL", "-o", dst, pick["download_url"]]).returncode == 0 and os.path.getsize(dst) > 1000:
            if "[" in pick["name"]: A.notes.append(f"« {name} » : police variable téléchargée (graisse par défaut, le gras peut manquer).")
            return dst
    return None

def palette(img_path, n=10):
    im = Image.open(img_path).convert("RGB"); im.thumbnail((400, 400))
    q = im.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[: n * 3]; counts = sorted(q.getcolors(), reverse=True)
    return [(hx(pal[i * 3:i * 3 + 3]), c) for c, i in counts]

def add_image(path):
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P") and im.convert("RGBA").getchannel("A").getextrema()[0] < 250:
        A.logos.append(path)                              # fond transparent → candidat logo
    for h, c in palette(path): A.colors[h] += c

def from_pptx(path):
    z = zipfile.ZipFile(path); names = z.namelist(); read = lambda n: z.read(n).decode("utf8", "ignore")
    th = next((n for n in names if re.match(r"ppt/theme/theme\d+\.xml", n)), None)
    if th:
        t = read(th)
        for role in ("dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6"):
            m = re.search(rf"<a:{role}>.*?(?:srgbClr val|lastClr)=\"([0-9A-Fa-f]{{6}})\"", t, re.S)
            if m: A.theme[role] = "#" + m.group(1).upper()
        for kind in ("majorFont", "minorFont"):
            m = re.search(rf"<a:{kind}>\s*<a:latin typeface=\"([^\"]+)\"", t)
            if m: A.fonts.append(m.group(1))
    big, small = Counter(), Counter()                     # police des gros textes = titres, des petits = texte
    for n in names:
        if re.match(r"ppt/(slides|slideLayouts|slideMasters)/[^/]+\.xml$", n):
            s = read(n)
            for c in re.findall(r'srgbClr val="([0-9A-Fa-f]{6})"', s): A.colors["#" + c.upper()] += 1
            for attrs, inner in re.findall(r"<a:rPr([^>]*)>(.*?)</a:rPr>", s, re.S):
                m, f = re.search(r'sz="(\d+)"', attrs), re.search(r'latin typeface="([^"+][^"]*)"', inner)
                if m and f: (big if int(m.group(1)) >= 2000 else small)[f.group(1)] += 1
    A.fonts = [f for f, _ in big.most_common(1)] + [f for f, _ in small.most_common(1)] + A.fonts
    # fond de la 1re diapo (ou de sa mise en page)
    for n in ["ppt/slides/slide1.xml", "ppt/slideLayouts/slideLayout1.xml"]:
        if n in names:
            m = re.search(r"<p:bg>.*?srgbClr val=\"([0-9A-Fa-f]{6})\"", read(n), re.S)
            if m: A.cover_bg = "#" + m.group(1).upper(); break
    tmp = tempfile.mkdtemp()
    for n in names:
        if n.startswith("ppt/media/") and n.lower().endswith((".png", ".svg", ".jpg", ".jpeg")):
            p = os.path.join(tmp, os.path.basename(n)); open(p, "wb").write(z.read(n))
            if p.endswith(".svg"): p = svg_png(p) or p
            if p.endswith(".png"):
                im = Image.open(p).convert("RGBA")
                if im.getchannel("A").getextrema()[0] < 250 and im.width > 80: A.logos.append(p)
    if any(n.startswith("ppt/fonts/") for n in names):
        A.notes.append("Polices embarquées au format EOT (inutilisable) : recherche du .ttf installé ou sur Google Fonts.")

def svg_png(p):
    d = tempfile.mkdtemp(); subprocess.run(["qlmanage", "-t", "-s", "1200", "-o", d, p], capture_output=True)
    out = glob.glob(os.path.join(d, "*.png"))
    if not out: return None
    im = Image.open(out[0]).convert("RGBA")                 # qlmanage rend sur fond blanc : on le détoure
    px = [(r, g, b, 0 if min(r, g, b) > 245 else a) for r, g, b, a in im.getdata()]
    im.putdata(px); bbox = im.getbbox()
    if bbox: im = im.crop(bbox)
    im.save(out[0]); return out[0]

def render_pdf(p):
    d = tempfile.mkdtemp(); subprocess.run(["qlmanage", "-t", "-s", "1600", "-o", d, p], capture_output=True)
    out = glob.glob(os.path.join(d, "*.png")); return out[0] if out else None

def from_key(p):
    pdf = os.path.join(tempfile.mkdtemp(), "k.pdf")
    subprocess.run(["osascript", "-e", f'tell application "Keynote"\nset d to open POSIX file "{p}"\nexport d to POSIX file "{pdf}" as PDF\nclose d saving no\nend tell'], capture_output=True)
    if os.path.exists(pdf): from_pdf(pdf)
    else: A.notes.append("Export Keynote impossible (Keynote absent ou refusé).")

def from_pdf(p):
    png = render_pdf(p)
    if png: add_image(png); A.cover_bg = A.cover_bg or palette(png, 4)[0][0]

def from_css(p):
    s = open(p).read()
    for name, h in re.findall(r"--([\w-]+)\s*:\s*(#[0-9A-Fa-f]{6}|#[0-9A-Fa-f]{3})\b", s):
        if len(h) == 4: h = "#" + "".join(c * 2 for c in h[1:])
        A.colors[h.upper()] += 5
        if any(k in name for k in ("primary", "brand", "accent")): A.theme.setdefault("accent1", h.upper())
    heads = [f.strip() for f in re.findall(r"(?:^|})\s*h[12][^{]*\{[^}]*font-family\s*:\s*['\"]?([^,;'\"]+)", s)]
    A.fonts += heads + [f.strip() for f in re.findall(r"font-family\s*:\s*['\"]?([^,;'\"]+)", s) if f.strip() not in heads]

def from_json(p):
    d = json.load(open(p))
    if "colors" in d and "cover_bg" in d["colors"]:
        return d                                           # déjà un theme.json
    for k, v in (d.get("colors") or {}).items():
        if isinstance(v, str) and v.startswith("#"):
            A.colors[v.upper()] += 5
            if k in ("primary", "brand", "accent"): A.theme.setdefault("accent1", v.upper())
    A.fonts += [v for v in (d.get("fonts") or {}).values() if isinstance(v, str)]

def build(out, name):
    os.makedirs(os.path.join(out, "fonts"), exist_ok=True)
    cols = [c for c, _ in A.colors.most_common(40)]
    chroma = [c for c in cols if not is_grey(c)]
    primary = A.theme.get("accent1") or (chroma[0] if chroma else "#2F5BEA")
    if lum(primary) > 0.5 and chroma: primary = next((c for c in chroma if lum(c) < 0.4), primary)
    cover_bg = A.cover_bg if A.cover_bg and not is_grey(A.cover_bg) else primary
    if contrast(cover_bg, "#FFFFFF") < 3: cover_bg = mix(cover_bg, "#000000", 0.35)
    darks = [c for c in cols if lum(c) < 0.05 and c != "#000000"]
    ink = darks[0] if darks else A.theme.get("dk1", "#151B24")
    greys = sorted([c for c in cols if is_grey(c) and 0.05 < lum(c) < 0.5], key=lum)
    body = greys[0] if greys else mix(ink, "#FFFFFF", 0.3)
    muted = greys[-1] if len(greys) > 1 else mix(ink, "#FFFFFF", 0.45)
    lights = [c for c in cols if is_grey(c) and 0.7 < lum(c) < 0.95]
    border = lights[0] if lights else "#E4E7ED"
    accents = [c for c in chroma if c != primary][:4]
    colors = {"cover_bg": cover_bg, "cover_mark": mix(cover_bg, "#FFFFFF", 0.25), "cover_eyebrow": mix(cover_bg, "#FFFFFF", 0.55),
              "cover_subtitle": mix(cover_bg, "#FFFFFF", 0.75), "cover_pill_bg": "#FFFFFF", "cover_pill_text": primary,
              "page_bg": A.theme.get("lt1", "#FFFFFF") if lum(A.theme.get("lt1", "#FFFFFF")) > 0.85 else "#FFFFFF",
              "surface": mix(border, "#FFFFFF", 0.6), "surface_blue": mix(primary, "#FFFFFF", 0.9), "border": border,
              "primary": primary, "ink": ink, "body": body, "muted": muted}
    for i, c in enumerate(accents): colors[f"accent_{i + 1}"] = c
    # polices
    fonts, used = {}, []
    families = [f for f in dict.fromkeys(A.fonts) if f and not f.startswith("+")]
    title_f = families[0] if families else None
    body_f = next((f for f in families[1:] if f != title_f), title_f)
    for key, fam, bold in (("title", title_f, True), ("title_regular", title_f, False), ("body", body_f, False), ("body_bold", body_f, True)):
        f = find_font(fam, bold) or (fam and google_font(fam, out, bold))
        if f and not f.startswith(out):
            dst = os.path.join(out, "fonts", os.path.basename(f)); shutil.copy(f, dst); f = dst
        fonts[key] = os.path.relpath(f, out) if f else FALLBACK[key]
        if not f and fam and f"« {fam} »" not in " ".join(A.notes): A.notes.append(f"Police « {fam} » introuvable (ni installée ni sur Google Fonts) : Arial à la place.")
    for i, ff in enumerate(A.font_files[:2]):
        dst = os.path.join(out, "fonts", os.path.basename(ff)); shutil.copy(ff, dst)
        for key in (("title", "title_regular") if i == 0 else ("body", "body_bold")): fonts[key] = os.path.relpath(dst, out)
    # logos : le plus clair = version sur fond sombre, le plus foncé = version sur fond clair
    assets = {}
    if A.logos:
        def mean_l(p):
            im = Image.open(p).convert("RGBA"); px = [p_ for p_ in im.resize((80, 80)).getdata() if p_[3] > 128]
            return sum(0.3 * r + 0.59 * g + 0.11 * b for r, g, b, _ in px) / max(len(px), 1)
        logos = sorted(dict.fromkeys(A.logos), key=mean_l)
        dark, light = logos[0], logos[-1]
        shutil.copy(dark, os.path.join(out, "logo-color.png")); assets["logo_color"] = "logo-color.png"
        if mean_l(light) > 200: shutil.copy(light, os.path.join(out, "logo-white.png"))
        else:                                              # blanchit la version couleur
            im = Image.open(dark).convert("RGBA"); a = im.getchannel("A")
            Image.merge("RGBA", (a.point(lambda _: 255),) * 3 + (a,)).save(os.path.join(out, "logo-white.png"))
        assets["logo_white"] = "logo-white.png"
    else:
        A.notes.append("Aucun logo trouvé (image à fond transparent) : couverture et pages sans logo.")
    A.notes = list(dict.fromkeys(A.notes))
    theme = {"_source": "extract_template.py", "name": name, "colors": colors, "fonts": fonts, "assets": assets,
             "labels": {"footer_left": name or "", "footer_right": ""}, "notes": A.notes}
    json.dump(theme, open(os.path.join(out, "theme.json"), "w"), ensure_ascii=False, indent=2)
    return theme

def preview(out):
    """Couverture + page d'étape rendues avec montage.py, côte à côte."""
    mp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "montage.py")
    code = open(mp).read().split("ap = argparse")[0]
    os.environ["VIDEO_TEMPLATE"] = out
    g = {"__file__": mp}; exec(code, g)
    c, p = os.path.join(out, "_c.png"), os.path.join(out, "_p.png")
    g["cover"]("Sur-titre", "Titre de la vidéo", "Sous-titre explicatif.", "Pastille", c)
    g["page"]("Étape 1 / 3", "Titre de l'étape", "Sous-titre de l'étape", (220, 330, 860, 1770), p)
    a, b = Image.open(c), Image.open(p); im = Image.new("RGB", (a.width + b.width + 40, a.height), "#888888")
    im.paste(a, (0, 0)); im.paste(b, (a.width + 40, 0)); im.thumbnail((1400, 1400)); im.save(os.path.join(out, "preview.png"))
    os.remove(c); os.remove(p)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("sources", nargs="+"); ap.add_argument("--out", required=True); ap.add_argument("--name", default="")
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    for s in a.sources:
        e = os.path.splitext(s)[1].lower()
        if e in (".pptx", ".potx", ".ppsx"): from_pptx(s)
        elif e == ".key": from_key(os.path.abspath(s))
        elif e == ".pdf": from_pdf(s)
        elif e in (".png", ".jpg", ".jpeg", ".webp"): add_image(s)
        elif e == ".svg":
            p = svg_png(s)
            if p: A.logos.append(p)
        elif e in (".css", ".scss"): from_css(s)
        elif e == ".json":
            ready = from_json(s)
            if ready: json.dump(ready, open(os.path.join(a.out, "theme.json"), "w"), ensure_ascii=False, indent=2); preview(a.out); print(a.out); return
        elif e in (".ttf", ".otf"): A.font_files.append(s)
        else: sys.exit(f"format non géré : {s}")
    t = build(a.out, a.name); preview(a.out)
    print(json.dumps({"colors": t["colors"], "fonts": t["fonts"], "assets": t["assets"], "notes": t["notes"]}, ensure_ascii=False, indent=1))

main()
