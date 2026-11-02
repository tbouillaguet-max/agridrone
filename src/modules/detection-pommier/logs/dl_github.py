"""Telechargement reprenable d'un depot GitHub (images) via raw.githubusercontent.
Usage: python dl_github.py owner/repo branch dest [prefix1,prefix2] [max_seconds]"""
import json, os, sys, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
repo, branch, dest = sys.argv[1], sys.argv[2], sys.argv[3]
prefixes = [p for p in (sys.argv[4].split(",") if len(sys.argv) > 4 else []) if p]
max_s = float(sys.argv[5]) if len(sys.argv) > 5 else 160
t0 = time.time()
manifest = os.path.join(dest, "_tree.json")
if os.path.exists(manifest):
    tree = json.load(open(manifest))
else:
    tree = json.load(urllib.request.urlopen(f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"))
    assert not tree.get("truncated"), "tree tronque"
    os.makedirs(dest, exist_ok=True); json.dump(tree, open(manifest, "w"))
files = [t for t in tree["tree"] if t["type"] == "blob" and (not prefixes or any(t["path"].startswith(p) for p in prefixes))]
have = {}
for d in {os.path.dirname(t["path"]) for t in files}:
    full = os.path.join(dest, d)
    if os.path.isdir(full):
        for e in os.scandir(full):
            have[os.path.join(d, e.name) if d else e.name] = True
todo = [t for t in files if t["path"] not in have]
t0 = time.time()
print(f"{len(files)} fichiers, {len(todo)} restants", flush=True)
def get(t):
    if time.time() - t0 > max_s: return "skip"
    p = os.path.join(dest, t["path"]); os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/" + urllib.parse.quote(t["path"])
    for _ in range(3):
        try:
            data = urllib.request.urlopen(url, timeout=30).read()
            open(p + ".part", "wb").write(data); os.replace(p + ".part", p); return "ok"
        except Exception as e:
            err = e
    return f"ERR {t['path']} {err}"
with ThreadPoolExecutor(int(os.environ.get("NT","64"))) as ex:
    res = list(ex.map(get, todo))
print("ok", res.count("ok"), "skip", res.count("skip"), "err", sum(r.startswith("ERR") for r in res))
for r in res:
    if r.startswith("ERR"): print(r)
print("RESTANT", res.count("skip") + sum(r.startswith("ERR") for r in res))
