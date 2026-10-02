#!/usr/bin/env node
// Pilote Chrome pour les vidéos de démo web — protocole DevTools (CDP), Node ≥ 22, zéro dépendance.
//
//   web.mjs launch [url] [--size 1440x900] [--lang en-US]   Chrome dédié (profil persistant ; --lang : locale)
//   web.mjs goto URL                         naviguer (onglet courant)
//   web.mjs tree [filtre]                    éléments visibles cliquables : libellé + centre (px CSS)
//   web.mjs click "Libellé" [n] | --sel CSS | X Y     déplacer le curseur (animé) puis cliquer
//   web.mjs hover "Libellé" [n] | --sel CSS | X Y     déplacer le curseur sans cliquer
//   web.mjs type "texte" [--delay 35]        frappe caractère par caractère (accents OK)
//   web.mjs paste "texte" | --file f         colle d'un bloc (code, YAML : évite l'auto-indentation de Monaco)
//   web.mjs key Enter | Tab | Escape | Meta+a …
//   web.mjs scroll DY [X Y]                  molette animée sous le curseur (ou en X Y)
//   web.mjs wait "Libellé" [s] | waitgone "Libellé" [s]
//   web.mjs shot nom                         capture → $PV_WORK_DIR/nom.png
//   web.mjs eval "js"                        évalue dans la page, affiche le résultat
//   web.mjs tabs | use main|popup|N          lister / choisir l'onglet piloté (popup OAuth…)
//   web.mjs cursor hide|show
//   web.mjs record start out.mp4 [--max 1920] | record stop | mark "libellé"
//   web.mjs quit                             ferme le Chrome dédié
//
// Coordonnées en px CSS du viewport. Le curseur (flèche + halo au clic) est dessiné dans la page :
// la capture CDP ne contient pas le pointeur système. État : $PV_WORK_DIR/web-state.json.
import { spawn, execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const PORT = +(process.env.PV_CHROME_PORT || 9333);
const WORK = process.env.PV_WORK_DIR || path.join(os.tmpdir(), "pv-web");
const PROFILE = process.env.PV_CHROME_PROFILE || path.join(os.homedir(), ".cache", "video-skill", "chrome");
const CHROME = process.env.PV_CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const FF = fs.existsSync("/usr/local/bin/ffmpeg") ? "/usr/local/bin/ffmpeg" : "ffmpeg";
const STATE = path.join(WORK, "web-state.json");
// couleur du halo de clic = couleur principale du template (VIDEO_TEMPLATE, sinon template/ du skill)
const TPL = process.env.VIDEO_TEMPLATE || path.join(path.dirname(process.argv[1]), "..", "template");
const PRIMARY = (() => { try { return JSON.parse(fs.readFileSync(path.join(TPL, "theme.json"), "utf8")).colors.primary; } catch { return "#2563EB"; } })();
const HALO = [1, 3, 5].map((i) => parseInt(PRIMARY.slice(i, i + 2), 16)).join(",");
fs.mkdirSync(WORK, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const readState = () => { try { return JSON.parse(fs.readFileSync(STATE, "utf8")); } catch { return {}; } };
const writeState = (p) => fs.writeFileSync(STATE, JSON.stringify({ ...readState(), ...p }, null, 1));
const die = (m) => { console.error(m); process.exit(1); };

// ---------------------------------------------------------------- CDP
async function http(p) { const r = await fetch(`http://127.0.0.1:${PORT}${p}`); return r.json(); }
async function browser() {
  const { webSocketDebuggerUrl } = await http("/json/version");
  const ws = new WebSocket(webSocketDebuggerUrl);
  await new Promise((ok, ko) => { ws.onopen = ok; ws.onerror = () => ko(new Error("CDP injoignable")); });
  let id = 0; const wait = new Map(), handlers = [];
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.id && wait.has(d.id)) { const [ok, ko] = wait.get(d.id); wait.delete(d.id); d.error ? ko(new Error(d.error.message)) : ok(d.result); }
    else if (d.method) handlers.forEach((h) => h(d));
  };
  const send = (method, params = {}, sessionId) => new Promise((ok, ko) => {
    const i = ++id; wait.set(i, [ok, ko]); ws.send(JSON.stringify({ id: i, method, params, sessionId }));
  });
  return { send, on: (h) => handlers.push(h), close: () => ws.close() };
}
async function pages(b) {
  const { targetInfos } = await b.send("Target.getTargets");
  return targetInfos.filter((t) => t.type === "page" && !t.url.startsWith("devtools://"));
}
// session sur l'onglet piloté : state.target, sinon l'onglet principal, sinon le premier
async function attach(b, targetId) {
  const st = readState(), ps = await pages(b);
  const t = ps.find((p) => p.targetId === (targetId || st.target)) || ps.find((p) => p.targetId === st.main) || ps[0];
  if (!t) die("aucun onglet — lancer d'abord « web.mjs launch »");
  const { sessionId } = await b.send("Target.attachToTarget", { targetId: t.targetId, flatten: true });
  const s = (m, p) => b.send(m, p, sessionId);
  s.targetId = t.targetId; s.sessionId = sessionId;
  return s;
}
async function evaluate(s, fn, ...args) {
  const expr = `(${fn})(...${JSON.stringify(args)})`;
  const r = await s("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true, userGesture: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
}

// ---------------------------------------------------------------- curseur dessiné dans la page
const CURSOR = (x, y, visible, halo) => {
  let c = document.getElementById("__pv_cursor");
  if (!c) {
    c = document.createElement("div"); c.id = "__pv_cursor";
    c.style.cssText = "position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;width:0;height:0;" +
      "transition:transform var(--pv-d,0ms) cubic-bezier(.45,0,.25,1);will-change:transform";
    c.innerHTML = '<div id="__pv_halo" style="position:absolute;left:-22px;top:-22px;width:44px;height:44px;border-radius:50%;' +
      `background:rgba(${halo},.30);border:2px solid rgba(${halo},.65);transform:scale(0);opacity:0"></div>` +
      '<svg width="30" height="30" viewBox="0 0 24 24" style="position:absolute;left:-3px;top:-2px;filter:drop-shadow(0 1px 2px rgba(0,0,0,.35))">' +
      '<path d="M4 2.5v17.2l4.6-4.4 2.9 6.6 3-1.3-2.9-6.5h6.4z" fill="#151B24" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.documentElement.appendChild(c);
    window.__pv = {
      move(x, y, ms) { c.style.setProperty("--pv-d", ms + "ms"); c.style.transform = `translate(${x}px,${y}px)`; },
      click() {
        c.querySelector("#__pv_halo").animate([{ transform: "scale(.2)", opacity: 1 }, { transform: "scale(1.25)", opacity: 0 }],
          { duration: 520, easing: "cubic-bezier(.2,.7,.3,1)" });
      },
    };
  }
  c.style.display = visible === false ? "none" : "";
  if (x != null) window.__pv.move(x, y, 0);
};
async function ensureCursor(s) {
  const st = readState(), p = st.cursor || { x: 40, y: 40 };
  await evaluate(s, CURSOR, p.x, p.y, st.cursorHidden ? false : true, HALO);
  return p;
}

// ---------------------------------------------------------------- recherche d'éléments
const FIND = (q, nth, sel) => {
  const out = [];
  const inter = (e) => e.matches("a,button,input,textarea,select,summary,label,[role=button],[role=link],[role=menuitem],[role=tab],[role=option],[role=checkbox],[role=switch],[role=radio],[role=combobox],[contenteditable=''],[contenteditable=true],[tabindex]:not([tabindex='-1'])") || getComputedStyle(e).cursor === "pointer";
  const name = (e) => (e.getAttribute("aria-label") || e.getAttribute("placeholder") || e.getAttribute("title") ||
    (e.tagName === "INPUT" && ["button", "submit"].includes(e.type) ? e.value : "") || e.innerText || e.textContent || "").trim().replace(/\s+/g, " ");
  const vis = (e, r) => r.width > 1 && r.height > 1 && getComputedStyle(e).visibility !== "hidden" && +getComputedStyle(e).opacity > 0.05;
  const walk = (doc, ox, oy) => {
    const els = sel ? doc.querySelectorAll(sel) : doc.querySelectorAll("body *");
    for (const e of els) {
      if (e.id === "__pv_cursor" || e.closest("#__pv_cursor")) continue;
      if (e.tagName === "IFRAME") { try { const r = e.getBoundingClientRect(); if (e.contentDocument) walk(e.contentDocument, ox + r.left, oy + r.top); } catch {} continue; }
      const r = e.getBoundingClientRect(); if (!vis(e, r)) continue;
      const n = name(e); if (!sel && (!n || n.length > 200)) continue;
      let score;
      if (sel) score = 0;
      else if (q == null) { if (!inter(e)) continue; score = 0; }
      else {
        const a = n.toLowerCase(), b = q.toLowerCase();
        score = a === b ? 0 : a.startsWith(b) ? 1 : a.includes(b) ? 2 : -1;
        if (score < 0) continue;
      }
      out.push({ e, n, score: score * 10 + (inter(e) ? 0 : 5), area: r.width * r.height,
        x: Math.round(ox + r.left + r.width / 2), y: Math.round(oy + r.top + r.height / 2), w: Math.round(r.width), h: Math.round(r.height) });
    }
  };
  walk(document, 0, 0);
  // garder l'élément le plus précis : on écarte un parent si un de ses descendants matche aussi bien
  const kept = out.filter((o) => !out.some((p) => p !== o && p.score <= o.score && o.e.contains(p.e)));
  kept.sort((a, b) => a.score - b.score || a.area - b.area);
  if (q == null && !sel) return kept.map(({ n, x, y, w, h }) => ({ n: n.slice(0, 80), x, y, w, h }));
  const hit = kept[nth || 0]; if (!hit) return null;
  const vw = innerWidth, vh = innerHeight;
  if (hit.y < 0 || hit.y > vh || hit.x < 0 || hit.x > vw) { hit.e.scrollIntoView({ block: "center", behavior: "smooth" }); return { scrolled: true }; }
  return { n: hit.n.slice(0, 80), x: hit.x, y: hit.y };
};
async function locate(s, argv) {
  let q = null, nth = 0, sel = null;
  if (argv[0] === "--sel") sel = argv[1];
  else if (argv.length >= 2 && /^-?\d+(\.\d+)?$/.test(argv[0]) && /^-?\d+(\.\d+)?$/.test(argv[1])) return { x: +argv[0], y: +argv[1] };
  else { q = argv[0]; nth = +(argv[1] || 0); }
  for (let i = 0; i < 3; i++) {
    const r = await evaluate(s, FIND, q, nth, sel);
    if (!r) die(`introuvable : ${sel || q}`);
    if (!r.scrolled) return r;
    await sleep(700);                                  // défilement doux vers l'élément
  }
  die(`hors écran : ${sel || q}`);
}

// ---------------------------------------------------------------- gestes
async function moveTo(s, x, y, ms) {
  const from = await ensureCursor(s);
  const d = Math.hypot(x - from.x, y - from.y);
  ms = ms ?? Math.round(Math.min(900, Math.max(280, 180 + d * 0.55)));   // vitesse naturelle
  await evaluate(s, (x, y, ms) => window.__pv.move(x, y, ms), x, y, ms);
  const n = Math.max(1, Math.round(ms / 50));
  for (let i = 1; i <= n; i++) {                       // vrais mouseMoved pour les survols (:hover, menus)
    const t = i / n, k = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
    await s("Input.dispatchMouseEvent", { type: "mouseMoved", x: from.x + (x - from.x) * k, y: from.y + (y - from.y) * k });
    await sleep(ms / n);
  }
  writeState({ cursor: { x, y } });
}
async function clickAt(s, x, y, count = 1) {
  await evaluate(s, () => window.__pv.click());
  for (const type of ["mousePressed", "mouseReleased"]) {
    await s("Input.dispatchMouseEvent", { type, x, y, button: "left", buttons: type === "mousePressed" ? 1 : 0, clickCount: count });
    if (type === "mousePressed") await sleep(70);
  }
}
const KEYS = {
  Enter: [13, "\r"], Tab: [9], Escape: [27], Backspace: [8], Delete: [46], Space: [32, " "],
  ArrowUp: [38], ArrowDown: [40], ArrowLeft: [37], ArrowRight: [39], Home: [36], End: [35], PageUp: [33], PageDown: [34],
};
const MODS = { Alt: 1, Control: 2, Ctrl: 2, Meta: 4, Cmd: 4, Shift: 8 };
const COMMANDS = { "Meta+a": "selectAll", "Meta+c": "copy", "Meta+x": "cut", "Meta+v": "paste", "Meta+z": "undo", "Meta+Shift+z": "redo" };
async function key(s, combo) {
  const parts = combo.split("+"), k = parts.pop();
  const modifiers = parts.reduce((m, p) => m | (MODS[p] || 0), 0);
  const [code, text] = KEYS[k] || [k.toUpperCase().charCodeAt(0), modifiers & ~8 ? undefined : k];
  const base = { key: k, windowsVirtualKeyCode: code, modifiers, code: KEYS[k] ? k : `Key${k.toUpperCase()}` };
  const commands = COMMANDS[combo] ? [COMMANDS[combo]] : undefined;
  await s("Input.dispatchKeyEvent", { type: text ? "keyDown" : "rawKeyDown", text, ...base, commands });
  await s("Input.dispatchKeyEvent", { type: "keyUp", ...base });
}
async function typeText(s, txt, delay) {
  for (const ch of txt) {
    if (ch === "\n") await key(s, "Enter");
    else {
      await s("Input.dispatchKeyEvent", { type: "keyDown", text: ch, unmodifiedText: ch, key: ch });
      await s("Input.dispatchKeyEvent", { type: "keyUp", key: ch });
    }
    await sleep(delay * (0.6 + Math.random() * 0.8));          // rythme humain, sans à-coups
  }
}

// ---------------------------------------------------------------- lancement / fenêtre
async function alive() { try { await http("/json/version"); return true; } catch { return false; } }
async function fitViewport(b, s, w, h) {
  const { windowId, bounds } = await b.send("Browser.getWindowForTarget", { targetId: s.targetId });
  if (bounds.windowState !== "normal") await b.send("Browser.setWindowBounds", { windowId, bounds: { windowState: "normal" } });
  for (let i = 0; i < 3; i++) {
    const v = await evaluate(s, () => [innerWidth, innerHeight]);
    const cur = (await b.send("Browser.getWindowBounds", { windowId })).bounds;
    if (v[0] === w && v[1] === h) return v;
    await b.send("Browser.setWindowBounds", { windowId, bounds: { left: 20, top: 30, width: cur.width + w - v[0], height: cur.height + h - v[1] } });
    await sleep(300);
  }
  return evaluate(s, () => [innerWidth, innerHeight]);
}

// ---------------------------------------------------------------- enregistrement
// Screencast CDP de l'onglet principal ; une popup (OAuth…) ouverte depuis lui est filmée à sa place
// jusqu'à sa fermeture. Les images arrivent à cadence variable (seulement quand l'écran change) :
// chaque image dure jusqu'à la suivante, puis ffmpeg rééchantillonne à 60 i/s constants.
async function recordRun(out, max) {
  const dir = out + ".frames"; fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
  const b = await browser(), st = readState();
  const frames = []; let current = null, stopping = false;
  const sessions = new Map();                                      // sessionId → targetId
  const start = async (targetId) => {
    const { sessionId } = await b.send("Target.attachToTarget", { targetId, flatten: true });
    sessions.set(sessionId, targetId);
    const s = (m, p) => b.send(m, p, sessionId);
    await s("Page.enable"); await s("Runtime.enable");
    // --lang ne change pas Intl (dates, nombres) sur macOS : on force la locale tant que l'enregistreur est attaché
    if (st.lang) await s("Emulation.setLocaleOverride", { locale: st.lang }).catch(() => {});
    try { await ensureCursor(Object.assign(s, { targetId })); } catch {}
    await s("Page.startScreencast", { format: "jpeg", quality: 90, maxWidth: max, maxHeight: max, everyNthFrame: 1 });
    current = sessionId;
  };
  const stop = async (sessionId) => { try { await b.send("Page.stopScreencast", {}, sessionId); } catch {} };
  b.on(async (m) => {
    if (m.method === "Page.screencastFrame") {
      b.send("Page.screencastFrameAck", { sessionId: m.params.sessionId }, m.sessionId).catch(() => {});
      if (m.sessionId !== current || stopping) return;
      const f = path.join(dir, `f${String(frames.length).padStart(6, "0")}.jpg`);
      fs.writeFileSync(f, Buffer.from(m.params.data, "base64"));
      frames.push({ f, t: m.params.metadata?.timestamp || Date.now() / 1000 });
      if (frames.length === 1) writeState({ recStart: frames[0].t, recOut: out });
    } else if (m.method === "Page.loadEventFired" && m.sessionId) {
      const s = (mm, p) => b.send(mm, p, m.sessionId);
      ensureCursor(s).catch(() => {});                               // la navigation a effacé le curseur
    } else if (m.method === "Target.targetCreated" && m.params.targetInfo.type === "page" && m.params.targetInfo.openerId) {
      await sleep(400); if (current) await stop(current); await start(m.params.targetInfo.targetId);
      writeState({ target: m.params.targetInfo.targetId });           // les commandes suivantes pilotent la popup
    } else if (m.method === "Target.targetDestroyed" && sessions.get(current) === m.params.targetId) {
      writeState({ target: st.main });
      await start(st.main);
    }
  });
  await b.send("Target.setDiscoverTargets", { discover: true });
  const s0 = await attach(b); await start(s0.targetId);
  writeState({ recPid: process.pid });
  await new Promise((r) => { process.on("SIGINT", r); process.on("SIGTERM", r); });
  stopping = true; const end = Date.now() / 1000;
  if (current) await stop(current);
  b.close();
  if (!frames.length) die("aucune image reçue (fenêtre Chrome minimisée ?)");
  const list = ["ffconcat version 1.0"];
  frames.forEach((fr, i) => list.push(`file '${fr.f}'`, `duration ${Math.max(0.001, (frames[i + 1]?.t ?? end) - fr.t).toFixed(4)}`));
  list.push(`file '${frames.at(-1).f}'`);
  fs.writeFileSync(path.join(dir, "list.txt"), list.join("\n"));
  const [w, h] = execFileSync(process.env.FFPROBE || FF.replace(/ffmpeg$/, "ffprobe"), ["-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", frames[0].f]).toString().trim().split(",").map((v) => Math.floor(+v / 2) * 2);
  execFileSync(FF, ["-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", path.join(dir, "list.txt"),
    "-vf", `fps=60,scale=${w}:${h}:force_original_aspect_ratio=decrease,pad=${w}:${h}:(ow-iw)/2:(oh-ih)/2:color=0xE4E7ED,setsar=1`,
    "-c:v", "libx264", "-preset", "fast", "-crf", "14", "-pix_fmt", "yuv420p", out]);
  if (!process.env.PV_KEEP_FRAMES) fs.rmSync(dir, { recursive: true, force: true });
  const secs = frames.at(-1).t - frames[0].t;
  fs.writeFileSync(out + ".log", `${frames.length} images sur ${(end - frames[0].t).toFixed(1)} s — cadence moyenne de capture ${(frames.length / Math.max(secs, 0.001)).toFixed(1)} i/s\n`);
  writeState({ recPid: null });
}

// ---------------------------------------------------------------- CLI
const [cmd, ...argv] = process.argv.slice(2);
const opt = (name, def) => { const i = argv.indexOf(name); if (i < 0) return def; const v = argv[i + 1]; argv.splice(i, 2); return v; };

if (cmd === "launch") {
  const [w, h] = opt("--size", readState().size || "1440x900").split("x").map(Number);
  const lang = opt("--lang", readState().lang || "");            // ex. en-US : dates, nombres, Accept-Language
  if (!(await alive())) {
    fs.mkdirSync(PROFILE, { recursive: true });
    spawn(CHROME, [`--remote-debugging-port=${PORT}`, `--user-data-dir=${PROFILE}`, "--no-first-run", "--no-default-browser-check",
      "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding", "--disable-background-timer-throttling",
      "--hide-crash-restore-bubble", "--disable-features=Translate,MediaRouter",
      ...(lang ? [`--lang=${lang}`, `--accept-lang=${lang},${lang.split("-")[0]}`] : []), argv[0] || "about:blank"],
    { detached: true, stdio: "ignore" }).unref();
    for (let i = 0; i < 120 && !(await alive()); i++) await sleep(250);   // jusqu'à 30 s (Mac chargé)
    if (!(await alive())) die("Chrome n'a pas démarré (port " + PORT + ")");
    await sleep(800);
  }
  const b = await browser(), s = await attach(b);
  if (argv[0]) { await s("Page.navigate", { url: argv[0] }); await sleep(1500); }
  writeState({ main: s.targetId, target: s.targetId, size: `${w}x${h}`, lang });
  const v = await fitViewport(b, s, w, h);
  await b.send("Browser.grantPermissions", { permissions: ["clipboardReadWrite", "clipboardSanitizedWrite"] }).catch(() => {});
  console.log(`Chrome prêt : viewport ${v[0]}x${v[1]}, profil ${PROFILE}`);
  b.close(); process.exit(0);
}
if (cmd === "record" && argv[0] === "run") { await recordRun(argv[1], +argv[2]); process.exit(0); }
if (cmd === "record" && argv[0] === "start") {
  const out = path.resolve(argv[1] || path.join(WORK, "web.mp4")), max = opt("--max", "1920");
  const st = readState(); if (st.recPid) { try { process.kill(st.recPid, 0); die("enregistrement déjà en cours (pid " + st.recPid + ")"); } catch {} }
  writeState({ recPid: null, recStart: null });
  const p = spawn(process.execPath, [process.argv[1], "record", "run", out, max], { detached: true, stdio: ["ignore", "ignore", fs.openSync(out + ".err", "w")] });
  p.unref();
  for (let i = 0; i < 40 && !readState().recStart; i++) await sleep(100);
  console.log(readState().recStart ? `enregistrement → ${out}` : `enregistrement lancé, pas encore d'image (voir ${out}.err)`);
  process.exit(0);
}
if (cmd === "record" && argv[0] === "stop") {
  const { recPid, recOut } = readState(); if (!recPid) die("aucun enregistrement en cours");
  process.kill(recPid, "SIGINT");
  for (let i = 0; i < 1200; i++) { try { process.kill(recPid, 0); await sleep(250); } catch { break; } }
  const log = fs.existsSync(recOut + ".log") ? fs.readFileSync(recOut + ".log", "utf8").trim() : "";
  console.log(`${recOut}\n${log}`); process.exit(0);
}
if (cmd === "mark") {
  const { recStart, recOut } = readState(); if (!recStart) die("aucun enregistrement en cours");
  const t = (Date.now() / 1000 - recStart).toFixed(2);
  fs.appendFileSync(recOut.replace(/\.mp4$/, "") + ".marks.txt", `${t}\t${argv.join(" ")}\n`); console.log(t); process.exit(0);
}
if (cmd === "quit") { const b = await browser(); await b.send("Browser.close").catch(() => {}); process.exit(0); }

const b = await browser();
if (cmd === "tabs") {
  const st = readState();
  (await pages(b)).forEach((p, i) => console.log(i, p.targetId === st.target ? "*" : " ", p.targetId === st.main ? "main " : p.openerId ? "popup" : "     ", p.title.slice(0, 50), "·", p.url.slice(0, 90)));
  process.exit(0);
}
if (cmd === "use") {
  const ps = await pages(b), st = readState();
  const t = argv[0] === "main" ? ps.find((p) => p.targetId === st.main) : argv[0] === "popup" ? ps.filter((p) => p.openerId).at(-1) : ps[+argv[0]];
  if (!t) die("onglet introuvable"); writeState({ target: t.targetId }); console.log(t.url); process.exit(0);
}
const s = await attach(b);
await s("Page.bringToFront").catch(() => {});
try {
  switch (cmd) {
    case "goto": await s("Page.enable"); await s("Page.navigate", { url: argv[0] }); await sleep(1500); await ensureCursor(s); break;
    case "tree": for (const e of await evaluate(s, FIND, null, 0, null)) if (!argv[0] || e.n.toLowerCase().includes(argv[0].toLowerCase())) console.log(`${e.x},${e.y}\t${e.w}x${e.h}\t${e.n}`); break;
    case "hover": case "click": case "dblclick": {
      const ms = opt("--ms", undefined);
      const r = await locate(s, argv); await moveTo(s, r.x, r.y, ms && +ms);
      if (cmd !== "hover") { await sleep(120); await clickAt(s, r.x, r.y, cmd === "dblclick" ? 2 : 1); }
      console.log(`${r.x},${r.y}${r.n ? "\t" + r.n : ""}`); break;
    }
    case "type": await typeText(s, argv[0], +opt("--delay", 35)); break;
    case "paste": {
      const f = opt("--file"); const txt = f ? fs.readFileSync(f, "utf8") : argv[0];
      await b.send("Browser.grantPermissions", { permissions: ["clipboardReadWrite", "clipboardSanitizedWrite"] }).catch(() => {});
      await evaluate(s, (t) => navigator.clipboard.writeText(t), txt);
      await key(s, "Meta+v"); break;
    }
    case "key": for (const k of argv) { await key(s, k); await sleep(80); } break;
    case "scroll": {
      const st = readState(); const x = argv[1] ? +argv[1] : st.cursor?.x ?? 700, y = argv[2] ? +argv[2] : st.cursor?.y ?? 450;
      const total = +argv[0], n = Math.max(6, Math.round(Math.abs(total) / 25));
      for (let i = 0; i < n; i++) { await s("Input.dispatchMouseEvent", { type: "mouseWheel", x, y, deltaX: 0, deltaY: total / n }); await sleep(16); }
      break;
    }
    case "wait": case "waitgone": {
      const until = Date.now() + 1000 * +(argv[1] || 30);
      for (;;) {
        const hit = await evaluate(s, FIND, argv[0], 0, null).catch(() => null);
        if (cmd === "wait" ? hit : !hit) { console.log("ok"); break; }
        if (Date.now() > until) die("délai dépassé");
        await sleep(250);
      }
      break;
    }
    case "shot": {
      const { data } = await s("Page.captureScreenshot", { format: "png" });
      const f = path.join(WORK, `${argv[0] || "shot"}.png`); fs.writeFileSync(f, Buffer.from(data, "base64")); console.log(f); break;
    }
    case "eval": console.log(JSON.stringify(await evaluate(s, new Function(`return (${argv[0]})`)), null, 1)); break;
    case "cursor": writeState({ cursorHidden: argv[0] === "hide" }); await ensureCursor(s); break;
    default: die(`commande inconnue : ${cmd}\n` + fs.readFileSync(process.argv[1], "utf8").split("\n").slice(1, 22).map((l) => l.replace(/^\/\/ ?/, "")).join("\n"));
  }
} finally { b.close(); }
process.exit(0);
