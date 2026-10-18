"""Run:  python check_groq.py
Shows which Groq models YOUR key can use, and tests one reply."""
import json
import urllib.request
import urllib.error

import main

key = main._groq_key()
if not key:
    raise SystemExit("No key found. Put your key in groq_key.txt next to main.py")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# 1) list models
req = urllib.request.Request("https://api.groq.com/openai/v1/models",
                             headers={"Authorization": f"Bearer {key}", "User-Agent": UA})
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        models = sorted(m["id"] for m in json.loads(r.read().decode())["data"])
    print("Models your key can use:")
    for m in models:
        print("  ", m)
except urllib.error.HTTPError as e:
    raise SystemExit(f"Could not list models: HTTP {e.code} (401 means the key is wrong)")

# 2) test a reply
print("\nTest reply:", main.ask_groq("Say hi in five words"))