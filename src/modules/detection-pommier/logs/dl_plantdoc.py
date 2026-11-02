import json, os, sys, urllib.request, urllib.parse
base = sys.argv[1]
repo = "pratikkayal/PlantDoc-Dataset"
n = 0
for split in ["train", "test"]:
    for cls in ["Apple leaf", "Apple Scab Leaf", "Apple rust leaf"]:
        url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(split + '/' + cls)}"
        items = json.load(urllib.request.urlopen(url))
        d = os.path.join(base, split, cls); os.makedirs(d, exist_ok=True)
        for it in items:
            if it["type"] != "file": continue
            p = os.path.join(d, it["name"])
            if os.path.exists(p): continue
            try:
                urllib.request.urlretrieve(it["download_url"], p); n += 1
            except Exception as e:
                print("ERR", it["name"], e)
        print(split, cls, len(items), flush=True)
print("DONE", n)
