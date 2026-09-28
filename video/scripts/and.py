#!/usr/bin/env python3
"""and.py tap X Y | text "Label" | type "txt" | swipe x1 y1 x2 y2 [ms] | long X Y | tree | shot name | key N
Coordinates are in device pixels (1280x2856)."""
import sys, subprocess, re, time, html, os
A = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
S = os.environ.get("PV_WORK_DIR", "/tmp")
def sh(*a): return subprocess.run([A, *a], capture_output=True).stdout
def dump():
    x = sh("exec-out", "uiautomator", "dump", "/dev/tty").decode("utf8", "replace")
    nodes = []
    for m in re.finditer(r'<node [^>]*>', x):
        n = m.group(0)
        g = lambda k: html.unescape((re.search(k + r'="([^"]*)"', n) or [None, ""])[1])
        b = [int(v) for v in re.findall(r'\d+', g("bounds"))]
        nodes.append(dict(text=g("text"), desc=g("content-desc"), click=g("clickable"), b=b))
    return nodes
c, *a = sys.argv[1:]
if c == "tap": sh("shell", "input", "tap", a[0], a[1])
elif c == "long": sh("shell", "input", "swipe", a[0], a[1], a[0], a[1], a[2] if len(a) > 2 else "1200")
elif c == "swipe": sh("shell", "input", "swipe", *a[:4], a[4] if len(a) > 4 else "400")
elif c == "key": sh("shell", "input", "keyevent", a[0])
elif c == "type":
    t = a[0].replace(" ", "%s").replace("'", "\\'").replace("?", "\\?").replace("(", "\\(").replace(")", "\\)").replace("&", "\\&")
    sh("shell", "input", "text", t)
elif c in ("text", "has"):
    for _ in range(int(a[1]) if len(a) > 1 else 8):
        for n in dump():
            if a[0] in (n["text"], n["desc"]) and n["b"]:
                if c == "text":
                    x0, y0, x1, y1 = n["b"]; sh("shell", "input", "tap", str((x0 + x1) // 2), str((y0 + y1) // 2))
                print("ok"); sys.exit(0)
        time.sleep(0.5)
    print("notfound")
elif c == "tree":
    for n in dump():
        if n["text"] or n["desc"]: print(n["b"], repr(n["text"]), repr(n["desc"]), "C" if n["click"] == "true" else "")
elif c == "shot":
    open(f"{S}/{a[0]}.png", "wb").write(sh("exec-out", "screencap", "-p"))
    subprocess.run(["sips", "-Z", "1000", f"{S}/{a[0]}.png"], capture_output=True); print(f"{S}/{a[0]}.png")
