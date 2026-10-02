#!/usr/bin/env python3
"""Paquet « lecteur web multilingue » : UNE vidéo (captures seules), une voix par langue, textes en HTML.

  package_player.py plan.json out_dir [--music default|<fichier>|none] [--music-gain -9] [--rates 0.75,1.25,1.5] [--fps 60] [--max-width 1920] [--max-file-mb 19.5]
                    [--base-url /tutorials/<nom>/]
  package_player.py plan.json out_dir --manifest-only    regénère manifeste, pistes et snippet sans refaire les médias

Au lieu d'une vidéo par langue (montage_web.py, textes incrustés), on publie un dossier statique :

  out_dir/
    index.html, player.css, player.js     le lecteur (copié depuis ../player/)
    manifest.json                         tout ce que le lecteur affiche, par langue
    media/video.mp4                       les captures, sans texte ni son
    media/voice_<l>.mp3                   la narration de chaque langue, calée sur la vidéo
    media/voice_<l>_<vitesse>.mp3         la même, pré-étirée sans changer la hauteur (ffmpeg atempo)
    tracks/subs_<l>.json                  sous-titres [{start, end, text}] (générés depuis la narration)
    tracks/chapters_<l>.json              une entrée par étape : {start, end, kind, section, title, sub, url, step, steps}
    brand/                                logo, symbole et police de titre du template
    captions/                             les mêmes sous-titres en .vtt et .srt, pour un autre usage (hors lecteur)
    snippet.mdx                           le lecteur à coller dans une page Mintlify (manifeste et pistes inclus)

Formats choisis pour être servis partout, y compris par Mintlify (docs.prisme.ai) qui ne sert ni .html,
ni .m4a, ni .vtt, ni (en pratique) .json/.yml, et refuse les fichiers de 20 Mo ou plus : MP3, MP4 réencodé
sous --max-file-mb, et pour Mintlify un snippet.mdx qui porte le manifeste ET les pistes (attribut
data-tutorial, JSON en base64) ; --base-url indique où les médias seront publiés (ex. /tutorials/sharepoint/).

plan.json (multilingue) :
{
  "langs": ["en", "fr"], "default_lang": "en", "labels": {"fr": "Français", "en": "English"},
  "cover": {"eyebrow": {…}, "title": {…}, "sub": {…}, "pill": {…}, "voice": {…}},
  "ui": {"fr": {"footer": "…"}, "en": {…}},                      (facultatif)
  "steps": [{"section": {…}, "title": {…}, "sub": {…}, "url": "app.exemple.com",
             "web": "clips/web_1.mp4", "trim": [4, 62], "cuts": "auto" | [[a, b], …],
             "voice": {…} (facultatif), "comments": [{"t": 12.4, "text": {"fr": "…", "en": "…"}}]}]
}
Chaque valeur {…} est {"<langue>": "texte"} (une chaîne simple vaut pour toutes les langues).
Les voix viennent de `voiceover.py plan.json` (champ "voices" de chaque élément).

Timeline commune : chaque voix occupe la durée de sa version la PLUS LONGUE, si bien que la même vidéo
convient à toutes les langues ; les coupes automatiques n'enlèvent jamais une image pendant qu'on parle.
"""
import argparse, base64, json, math, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import timeline  # noqa: E402
from timeline import FF, dur, size  # noqa: E402

TAIL, VO_TAIL, VO_DELAY, COVER_MIN = 0.6, 0.5, 0.4, 2.0    # rythme : retour d usage du 01/10, 3 s de pause = trop


def tr(value, lang):
    return value.get(lang, "") if isinstance(value, dict) else (value or "")


def run(args):
    subprocess.run([FF, "-v", "error", "-y", *args], check=True)


def ts(t, sep="."):
    ms = int(round(t * 1000))                       # en millisecondes entières : jamais « 60.000 »
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}"


def cue_text(text):
    """Texte de cue VTT/SRT sûr : pas de ligne vide ni de « --> », entités HTML échappées."""
    return " ".join(str(text).split()).replace("&", "&amp;").replace("<", "&lt;").replace("-->", "→")


def voice_of(item, lang):
    return (item.get("voices") or {}).get(lang)


class Package:
    def __init__(self, plan_path, out, rates, fps, max_width, max_mb=19.5, base_url="./", music=None, music_gain=-9.0):
        self.plan = json.load(open(plan_path))
        self.base = os.path.dirname(os.path.abspath(plan_path))
        self.out, self.rates, self.fps, self.max_width, self.max_mb = out, rates, fps, max_width, max_mb
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.langs = self.plan["langs"]
        self.tmp = tempfile.mkdtemp(prefix="pvplayer-")
        tpl = os.environ.get("VIDEO_TEMPLATE") or os.path.join(HERE, "..", "template")
        self.tpl, self.theme = tpl, json.load(open(os.path.join(tpl, "theme.json")))
        if music == "default":                           # fond musical du template (template/music/*)
            folder = os.path.join(tpl, "music")
            found = sorted(f for f in os.listdir(folder) if not f.startswith(".")) if os.path.isdir(folder) else []
            music = os.path.join(folder, found[0]) if found else None
        self.music = music if music and music != "none" else None
        self.music_gain = music_gain
        self.segments = []        # (rendu différé → fichier vidéo, durée)
        self.voices = []          # (début global, élément, durée commune)
        self.chapters = []        # (début, fin, élément de plan, kind, index)

    def path(self, p):
        return p if os.path.isabs(p) else os.path.join(self.base, p)

    # -- durée commune d'une voix : la plus longue de ses langues
    def common(self, item):
        ds = [voice_of(item, l)["duration"] for l in self.langs if voice_of(item, l)]
        if len(ds) != len([l for l in self.langs if tr(item.get("voice") or item.get("text"), l)]):
            sys.exit(f"voix manquante pour {tr(item.get('voice') or item.get('text'), self.langs[0])[:50]!r} — lancer voiceover.py")
        return max(ds) if ds else 0.0

    def geometry(self):
        src = self.path(self.plan["steps"][0]["web"])
        w, h = size(src)
        if w > self.max_width:
            w, h = self.max_width, round(h * self.max_width / w)
        self.W, self.H = w // 2 * 2, h // 2 * 2

    def render_frame(self, src, t, length, name):
        """Segment figé sur une image du clip (couverture)."""
        img = os.path.join(self.tmp, name + ".png")
        run(["-ss", f"{t:.3f}", "-i", src, "-frames:v", "1", img])
        out = os.path.join(self.tmp, name + ".mp4")
        run(["-loop", "1", "-t", f"{length:.3f}", "-i", img, "-vf",
             f"fps={self.fps},scale={self.W}:{self.H}:flags=lanczos,setsar=1,format=yuv420p",
             "-t", f"{length:.3f}", "-c:v", "libx264", "-preset", "slow", "-crf", "22", "-tune", "stillimage", out])
        return self.check(out, length)

    def render_step(self, src, ranges, length, name):
        """Plages gardées du clip, puis dernière image tenue jusqu'à `length`.
        En deux passes : dans une même chaîne concat → tpad, tpad ne prolonge rien (segments ~1,2 s trop
        courts, la voix dérivait) et tpad stop=-1 ne termine jamais ; appliqué au fichier, il est fiable."""
        n = len(ranges)
        fc = (f"[0:v]fps={self.fps},split={n}" + "".join(f"[s{k}]" for k in range(n)) + ";"
              + "".join(f"[s{k}]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS[t{k}];" for k, (a, b) in enumerate(ranges))
              + "".join(f"[t{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0,"
              f"scale={self.W}:{self.H}:flags=lanczos,setsar=1,format=yuv420p[v]")
        body = os.path.join(self.tmp, name + "_body.mp4")
        run(["-i", src, "-filter_complex", fc, "-map", "[v]", "-r", str(self.fps), "-c:v", "libx264", "-preset", "slow", "-crf", "18", body])
        pad = max(0.0, length - dur(body)) + 1.0
        out = os.path.join(self.tmp, name + ".mp4")
        run(["-i", body, "-vf", f"tpad=stop_mode=clone:stop_duration={pad:.3f}", "-r", str(self.fps), "-t", f"{length:.3f}",
             "-c:v", "libx264", "-preset", "slow", "-crf", "22", out])
        return self.check(out, length)

    def check(self, path, length):
        """Un segment doit durer exactement ce que la timeline prévoit, à une image près."""
        got = dur(path)
        if abs(got - length) > 1.5 / self.fps:
            sys.exit(f"{os.path.basename(path)} : {got:.3f} s rendus pour {length:.3f} s prévus — la voix dériverait")
        return path

    # -- 1. timeline : couverture, puis chaque étape (coupes + voix placées sur la durée commune)
    def build_timeline(self):
        t = 0.0
        cover = self.plan.get("cover")
        if cover:
            d = self.common(cover) if cover.get("voice") else None
            length = max(COVER_MIN, (VO_DELAY + d + VO_TAIL) if d else 0)
            first = self.plan["steps"][0]
            src0, t0 = self.path(first["web"]), first.get("trim", [0])[0]
            self.segments.append((lambda src0=src0, t0=t0, length=length: self.render_frame(src0, t0, length, "cover"), length))
            if d: self.voices.append((VO_DELAY, cover, d))
            self.chapters.append((0.0, length, cover, "cover", 0))
            t = length
        for i, st in enumerate(self.plan["steps"]):
            src = self.path(st["web"])
            total = dur(src)
            trim = [st.get("trim", [0, total])[0], min(st.get("trim", [0, total])[1], total)]
            items = ([(trim[0] + VO_DELAY, st)] if st.get("voice") else []) + [(c["t"], c) for c in st.get("comments", [])]
            items = sorted(((ti, it, self.common(it)) for ti, it in items), key=lambda x: x[0])
            items = [x for x in items if x[2] > 0]         # élément sans texte dans aucune langue : muet
            vs = [(ti, d) for ti, _, d in items]
            cuts = st.get("cuts", [])
            if cuts == "auto":
                cuts = timeline.auto_cuts(src, trim, vs)
            ranges = timeline.keep_ranges(trim, cuts)
            starts = timeline.place(vs, ranges)
            body = sum(b - a for a, b in ranges)
            end = max((at + d for at, (_, _, d) in zip(starts, items)), default=0)
            length = max(body + TAIL, end + VO_TAIL)
            for at, (_, it, d) in zip(starts, items):
                self.voices.append((t + at, it, d))
            self.segments.append((lambda src=src, ranges=ranges, length=length, i=i: self.render_step(src, ranges, length, f"step{i + 1:02d}"), length))
            self.chapters.append((t, t + length, st, "step", i + 1))
            print(f"étape {i + 1:2d} : {length:5.1f} s  ({len(cuts)} coupes, {len(items)} voix)", flush=True)
            t += length
        self.total = t

    # -- 2. médias
    def render_video(self):
        files = [render() for render, _ in self.segments]
        lst = os.path.join(self.tmp, "segments.txt")
        open(lst, "w").write("".join(f"file '{p}'\n" for p in files))
        video = os.path.join(self.out, "media", "video.mp4")
        run(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", video])
        if abs(dur(video) - self.total) > 0.2:    # dérive de concat tolérée (~12 images à 60 i/s)
            sys.exit(f"video.mp4 : {dur(video):.2f} s pour {self.total:.2f} s de timeline")
        crf = 24                                   # au-delà du plafond : réencodage un cran plus compressé
        while os.path.getsize(video) > self.max_mb * 1e6 and crf <= 36:
            tmp = video + ".tmp.mp4"
            run(["-i", video, "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-movflags", "+faststart", tmp])
            os.replace(tmp, video); crf += 2
        print(f"vidéo : {os.path.getsize(video) / 1e6:.1f} Mo, {self.total:.1f} s", flush=True)

    def render_music(self):
        """Fond musical à la longueur de la vidéo : rogné avant son silence final, bouclé avec un fondu enchaîné,
        fondus d'entrée/sortie, gain --music-gain. Le ducking (baisse sous la voix) se fait au mixage."""
        if not self.music:
            return None
        src, total, xf = self.music, self.total, 4.0
        err = subprocess.run([FF, "-hide_banner", "-i", src, "-af", "silencedetect=n=-45dB:d=0.3", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        tails = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", err)]
        length = dur(src)
        usable = tails[-1] if tails and tails[-1] > length - 5 else length
        loops = max(1, math.ceil((total + xf) / (usable - xf)))
        ins, fc = [], []
        for k in range(loops):
            ins += ["-i", src]
            fc.append(f"[{k}:a]atrim=0:{usable:.3f},aresample=48000,aformat=channel_layouts=stereo[m{k}]")
        chain = "[m0]"
        for k in range(1, loops):
            fc.append(f"{chain}[m{k}]acrossfade=d={xf}:c1=tri:c2=tri[x{k}]")
            chain = f"[x{k}]"
        fc.append(f"{chain}atrim=0:{total:.3f},afade=t=in:d=1.5,afade=t=out:st={max(0, total - 3):.3f}:d=3,"
                  f"volume={self.music_gain}dB[music]")
        path = os.path.join(self.tmp, "music.wav")
        run([*ins, "-filter_complex", ";".join(fc), "-map", "[music]", path])
        print(f"musique : {os.path.basename(src)} ×{loops}, {self.music_gain} dB", flush=True)
        return path

    def render_voices(self):
        self.voice_files = {}
        music = self.render_music()
        for l in self.langs:
            placed = [(at, voice_of(it, l)) for at, it, _ in self.voices if voice_of(it, l)]
            if not placed:
                sys.exit(f"aucune voix en {l} — lancer voiceover.py, ou retirer {l} de \"langs\"")
            ins, fc = [], []
            for k, (at, v) in enumerate(placed):
                ins += ["-i", self.path(v["file"])]
                fc.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={int(at * 1000)}:all=1[a{k}]")
            voice_out = "[out]" if not music else "[voice]"
            fc.append("".join(f"[a{k}]" for k in range(len(placed)))
                      + f"amix=inputs={len(placed)}:normalize=0:duration=longest,apad,atrim=0:{self.total:.3f}{voice_out}")
            if music:
                # la voix pilote un compresseur sur la musique : ~-8 dB de plus pendant qu'on parle (ducking)
                k = len(placed)
                ins += ["-i", music]
                fc.append("[voice]asplit=2[v1][v2]")
                fc.append(f"[{k}:a][v2]sidechaincompress=threshold=0.015:ratio=8:attack=30:release=600:makeup=1[duck]")
                fc.append("[v1][duck]amix=inputs=2:normalize=0:duration=first[out]")
            base = os.path.join(self.out, "media", f"voice_{l}.mp3")
            mp3 = (["-c:a", "libmp3lame", "-b:a", "128k", "-ac", "2"] if music      # musique : stéréo
                   else ["-c:a", "libmp3lame", "-b:a", "96k", "-ac", "1"])         # une voix seule : mono 96 kb/s
            run([*ins, "-filter_complex", ";".join(fc), "-map", "[out]", *mp3, base])
            files = {"1": f"media/voice_{l}.mp3"}
            for r in self.rates:
                name = f"media/voice_{l}_{r:g}.mp3"
                run(["-i", base, "-af", f"atempo={r}", *mp3, os.path.join(self.out, name)])
                files[f"{r:g}"] = name
            self.voice_files[l] = files
            print(f"voix {l} : {len(placed)} phrases, {len(self.rates)} vitesses", flush=True)

    # -- 3. pistes texte
    def write_tracks(self):
        steps = len(self.plan["steps"])
        os.makedirs(os.path.join(self.out, "captions"), exist_ok=True)
        for l in self.langs:
            subs = [{"start": round(at, 3), "end": round(at + v["duration"], 3), "text": v["text"]}
                    for at, it, _ in self.voices for v in [voice_of(it, l)] if v]
            chapters = [{"start": round(a, 3), "end": round(b, 3), "kind": kind, "step": idx, "steps": steps,
                         "section": tr(it.get("section"), l) or (tr(it.get("eyebrow"), l) if kind == "cover" else tr(it.get("title"), l)),
                         "title": tr(it.get("title"), l),
                         "sub": tr(it.get("sub"), l), "url": it.get("url", "")}
                        for a, b, it, kind, idx in self.chapters]
            json.dump(subs, open(os.path.join(self.out, "tracks", f"subs_{l}.json"), "w"), ensure_ascii=False, indent=0)
            json.dump(chapters, open(os.path.join(self.out, "tracks", f"chapters_{l}.json"), "w"), ensure_ascii=False, indent=0)
            vtt = ["WEBVTT", ""] + [f"{ts(c['start'])} --> {ts(c['end'])}\n{cue_text(c['text'])}\n" for c in subs]
            srt = [f"{k + 1}\n{ts(c['start'], ',')} --> {ts(c['end'], ',')}\n{cue_text(c['text'])}\n" for k, c in enumerate(subs)]
            open(os.path.join(self.out, "captions", f"{l}.vtt"), "w").write("\n".join(vtt))
            open(os.path.join(self.out, "captions", f"{l}.srt"), "w").write("\n".join(srt))

    # -- 4. manifeste + lecteur + charte
    def write_manifest(self):
        th, brand = self.theme, {}
        os.makedirs(os.path.join(self.out, "brand"), exist_ok=True)
        for key in ("logo_color", "logo_white", "mark_light_blue"):
            p = th.get("assets", {}).get(key)
            if p and os.path.exists(os.path.join(self.tpl, p)):
                shutil.copy(os.path.join(self.tpl, p), os.path.join(self.out, "brand", os.path.basename(p)))
                brand[key] = "brand/" + os.path.basename(p)
        font = th.get("fonts", {}).get("title", "")
        font = font if os.path.isabs(font) else os.path.join(self.tpl, font)
        if os.path.exists(font) and font.lower().endswith((".ttf", ".otf", ".woff", ".woff2")):
            shutil.copy(font, os.path.join(self.out, "brand", os.path.basename(font)))
            brand["title_font"] = "brand/" + os.path.basename(font)
        brand["colors"] = {k: v for k, v in th.get("colors", {}).items() if isinstance(v, str)}
        cover = self.plan.get("cover") or {}
        manifest = {
            "version": 1,
            "langs": self.langs,
            "default_lang": self.plan.get("default_lang", self.langs[0]),
            "labels": self.plan.get("labels", {}),
            "ui": self.plan.get("ui", {}),
            "cover": {l: {k: tr(cover.get(k), l) for k in ("eyebrow", "title", "sub", "pill")} for l in self.langs},
            "video": {"src": "media/video.mp4", "width": self.W, "height": self.H, "duration": round(self.total, 3)},
            "rates": [1] + self.rates,
            "voices": self.voice_files,
            "subtitles": {l: f"tracks/subs_{l}.json" for l in self.langs},
            "chapters": {l: f"tracks/chapters_{l}.json" for l in self.langs},
            "brand": brand,
        }
        json.dump(manifest, open(os.path.join(self.out, "manifest.json"), "w"), ensure_ascii=False, indent=1)
        # page de doc (Mintlify ne sert pas de .json) : manifeste + pistes inclus dans l'attribut data-tutorial
        inline = {**manifest, "tracks": {l: {k: json.load(open(os.path.join(self.out, "tracks", f"{k}_{l}.json")))
                                              for k in ("chapters", "subs")} for l in self.langs}}
        blob = base64.b64encode(json.dumps(inline, ensure_ascii=False, separators=(",", ":")).encode()).decode()
        open(os.path.join(self.out, "snippet.mdx"), "w").write(
            f'<div className="pv-host not-prose" data-base="{self.base_url}" data-tutorial="{blob}"></div>\n')
        for f in ("index.html", "player.css", "player.js"):
            shutil.copy(os.path.join(HERE, "..", "player", f), os.path.join(self.out, f))

    def build(self, manifest_only=False):
        for d in ("media", "tracks"):
            os.makedirs(os.path.join(self.out, d), exist_ok=True)
        self.geometry()
        self.build_timeline()
        if manifest_only:                      # médias déjà rendus : on ne regénère que les textes
            self.voice_files = {l: {("1" if r == 1 else f"{r:g}"): f"media/voice_{l}{'' if r == 1 else f'_{r:g}'}.mp3"
                                    for r in [1] + self.rates} for l in self.langs}
            missing = [f for v in self.voice_files.values() for f in v.values() if not os.path.exists(os.path.join(self.out, f))]
            if missing or not os.path.exists(os.path.join(self.out, "media", "video.mp4")):
                sys.exit(f"--manifest-only : médias absents ({missing[:3] or 'media/video.mp4'}) — lancer sans l'option")
            if abs(dur(os.path.join(self.out, "media", "video.mp4")) - self.total) > 0.2:   # même tolérance qu au rendu
                sys.exit("--manifest-only : la timeline a changé (durées, coupes ou voix) — refaire les médias")
        else:
            self.render_video()
            self.render_voices()
        self.write_tracks()
        self.write_manifest()
        big = [(os.path.relpath(os.path.join(d, f), self.out), os.path.getsize(os.path.join(d, f)) / 1e6)
               for d, _, fs in os.walk(self.out) for f in fs if os.path.getsize(os.path.join(d, f)) > self.max_mb * 1e6]
        for f, mb in big:
            print(f"⚠ {f} : {mb:.1f} Mo, au-dessus de {self.max_mb} Mo (refusé par Mintlify)")
        print(f"{self.out} : {self.total:.1f} s, {len(self.langs)} langues ({', '.join(self.langs)})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan"); ap.add_argument("out")
    ap.add_argument("--rates", default="0.75,1.25,1.5", help="vitesses pré-étirées (vide = aucune)")
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--max-width", type=int, default=1920)
    ap.add_argument("--max-file-mb", type=float, default=19.5, help="plafond par fichier (Mintlify : < 20 Mo)")
    ap.add_argument("--base-url", default="./", help="URL où le dossier sera publié, pour snippet.mdx (ex. /tutorials/sharepoint/)")
    ap.add_argument("--manifest-only", action="store_true", help="ne regénérer que manifeste, pistes et snippet")
    ap.add_argument("--music", default="none", help="fond musical : chemin, « default » (template/music/) ou « none »")
    ap.add_argument("--music-gain", type=float, default=-9.0, help="gain du fond musical en dB (avant ducking)")
    a = ap.parse_args()
    rates = sorted({float(r) for r in a.rates.split(",") if r.strip()} - {1.0})   # 1 = la voix de base
    Package(a.plan, a.out, rates, a.fps, a.max_width, a.max_file_mb, a.base_url, a.music, a.music_gain).build(a.manifest_only)


if __name__ == "__main__":
    main()
