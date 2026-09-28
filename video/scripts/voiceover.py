#!/usr/bin/env python3
"""Génère la narration d'un plan.json avec Voicebox (API locale http://127.0.0.1:17493).

  voiceover.py plan.json [--profile Me] [--engine qwen] [--instruct "..."] [--force]

Pour chaque étape portant un champ "voice" (texte), écrit vo/step_<n>.wav à côté du plan et
renseigne "voice_file" + "voice_duration" dans le plan. La couverture peut aussi avoir "voice".
Une génération bloquée (statut « loading_model » sans activité, vu le 26/09) est annulée puis
relancée automatiquement.
"""
import argparse, json, os, sys, time, urllib.request

B = os.environ.get("VOICEBOX_URL", "http://127.0.0.1:17493")

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
    ap.add_argument("plan"); ap.add_argument("--profile", required=True, help="nom ou id du profil de voix Voicebox")
    ap.add_argument("--engine", default=None); ap.add_argument("--instruct", default=None)
    ap.add_argument("--language", default="fr"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    plan = json.load(open(a.plan)); base = os.path.dirname(os.path.abspath(a.plan))
    os.makedirs(os.path.join(base, "vo"), exist_ok=True)
    profiles = call("GET", "/profiles")
    prof = next((p for p in profiles if p["name"] == a.profile or p["id"] == a.profile), None)
    if not prof: sys.exit(f"profil {a.profile!r} introuvable : {[p['name'] for p in profiles]}")
    items = ([("cover", plan["cover"])] if plan.get("cover", {}).get("voice") else []) + \
            [(str(i + 1), s) for i, s in enumerate(plan["steps"]) if s.get("voice")]
    for key, it in items:
        out = os.path.join(base, "vo", f"step_{key}.wav")
        if os.path.exists(out) and it.get("voice_text_done") == it["voice"] and not a.force:
            print(f"{key}: déjà généré"); continue
        body = {"profile_id": prof["id"], "text": it["voice"], "language": a.language, "normalize": True}
        if a.engine: body["engine"] = a.engine
        if a.instruct: body["instruct"] = a.instruct
        t0 = time.time(); g = call("POST", "/generate", body)
        h = wait(g["id"])
        open(out, "wb").write(call("GET", f"/audio/{g['id']}", raw=True))
        it.update(voice_file=os.path.relpath(out, base), voice_duration=round(h["duration"], 2), voice_text_done=it["voice"])
        print(f"{key}: {h['duration']:.1f} s de voix en {time.time() - t0:.0f} s", flush=True)
        json.dump(plan, open(a.plan, "w"), ensure_ascii=False, indent=2)

main()
