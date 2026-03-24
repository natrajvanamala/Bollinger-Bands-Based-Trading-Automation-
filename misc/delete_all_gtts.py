#!/usr/bin/env python3
import json
import time
from login import login

angel = login()

# Fix SmartAPI bug
orig = angel._request
def patched(route, method, params=None):
    try:
        return orig(route, method, params)
    except KeyError as e:
        if str(e) == "'message'":
            return {"status": True, "data": []}
        raise
angel._request = patched

# Fetch only NEW (skips CANCELLED entirely)
all_gtts = []
page     = 1

while True:
    raw = angel.gttLists(["NEW"], page, 500)
    if isinstance(raw, str):
        raw = json.loads(raw)
    batch = raw.get("data", []) if isinstance(raw, dict) else []
    if not batch:
        break
    all_gtts.extend(batch)
    print(f"📄 Page {page}: {len(batch)} GTTs fetched")
    if len(batch) < 500:
        break
    page += 1

print(f"\n🎯 Total to delete: {len(all_gtts)}\n")

deleted = 0
failed  = 0

for gtt in all_gtts:
    gtt_id = str(int(float(gtt["id"])))
    symbol = gtt.get("tradingsymbol", "")
    try:
        payload = {
            "id":          gtt_id,
            "symboltoken": gtt.get("symboltoken"),
            "exchange":    gtt.get("exchange")
        }
        res = angel.gttCancelRule(payload)
        if isinstance(res, str):
            res = json.loads(res)
        if isinstance(res, dict) and res.get("status"):
            print(f"✅ {symbol:<15} {gtt_id}")
            deleted += 1
        else:
            msg = res.get("message", str(res)) if isinstance(res, dict) else str(res)
            print(f"❌ {symbol:<15} {gtt_id} → {msg}")
            failed += 1
    except Exception as e:
        print(f"❌ {symbol:<15} {gtt_id} → {e}")
        failed += 1
    time.sleep(0.1)

print(f"\n✅ Deleted: {deleted}  ❌ Failed: {failed}")
