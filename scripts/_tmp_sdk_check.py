"""Temp: verify cursor-sdk 0.1.7 bridge + opus-4-8 variant matching."""
import re
import os

env = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(".env", encoding="utf-8").read(), re.M))
os.environ.setdefault("CURSOR_API_KEY", env.get("CURSOR_API_KEY", "").strip().strip('"'))

from cursor_sdk import Cursor

models = Cursor.models.list()
opus = next(m for m in models if m.id == "claude-opus-4-8")
print("bridge OK, models:", len(models))
print("opus params:", [p.id for p in (opus.parameters or [])])
target = {"thinking": "true", "context": "300k", "effort": "xhigh", "fast": "false"}
for v in opus.variants or []:
    combo = {p.id: p.value for p in v.params}
    if all(combo.get(k) == val for k, val in target.items()):
        print("matching variant:", combo)
