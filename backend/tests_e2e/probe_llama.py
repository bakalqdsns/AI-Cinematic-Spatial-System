"""Probe llama-server slot count and 503 behaviour."""
import urllib.request, json

def get(path):
    return urllib.request.urlopen(f"http://127.0.0.1:8080{path}", timeout=3).read().decode()

print("health:", get("/health"))
try:
    props = get("/props")
    j = json.loads(props)
    print("props keys:", list(j.keys())[:10])
    for k in ("default_generation_settings", "build_info", "total_slots", "model"):
        if k in j:
            print(f"  {k}:", j[k])
except Exception as e:
    print("props err:", e)

try:
    slots = get("/slots")
    j = json.loads(slots)
    print(f"slots: total={len(j) if isinstance(j, list) else 'n/a'}")
except Exception as e:
    print("slots err:", e)