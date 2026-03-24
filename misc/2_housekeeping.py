#=========#
# IMPORTS #
#=========#
import json
import time
import os
import pandas as pd
from datetime import datetime
from login import login

#========#
# LOGIN  #
#========#
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

print("="*70)
print("🧹 GTT HOUSEKEEPING")
print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*70)

#===============#
# LOAD CSV      #
#===============#
try:
    df = pd.read_csv("output.csv")
except FileNotFoundError:
    print("❌ output.csv not found! Run 1_main.py first.")
    exit()

print(f"\n📂 Loaded {len(df)} stocks from output.csv\n")

#===================#
# FETCH ALL GTTs    #
#===================#
all_gtts = []
page     = 1
while True:
    raw = angel.gttLists(["FORALL"], page, 500)
    if isinstance(raw, str):
        raw = json.loads(raw)
    batch = raw.get("data", []) if isinstance(raw, dict) else []
    if not batch:
        break
    all_gtts.extend(batch)
    if len(batch) < 500:
        break
    page += 1

# id → gtt object lookup
gtt_map = {int(g["id"]): g for g in all_gtts if g.get("id")}
print(f"📥 Fetched {len(gtt_map)} GTT rules from Angel One\n")

#===================#
# CANCEL HELPER     #
#===================#
def cancel(rule_id, gtt_obj):
    if not gtt_obj:
        return "Not Found"
    try:
        payload = {
            "id":          str(rule_id),
            "symboltoken": str(gtt_obj.get("symboltoken", "")),
            "exchange":    str(gtt_obj.get("exchange", ""))
        }
        res = angel.gttCancelRule(payload)
        if isinstance(res, str):
            res = json.loads(res)
        if isinstance(res, dict) and res.get("status"):
            return "Deleted"
        elif isinstance(res, dict) and res.get("errorcode") == "AB9028":
            return "Already Removed"
        return f"Failed"
    except Exception as e:
        return "Already Removed" if "AB9028" in str(e) else f"Error"

#===================#
# PROCESS STOCKS    #
#===================#
print("="*70)
print("🔍 PROCESSING STOCKS")
print("="*70)

results      = []
deleted_buy  = 0
deleted_sell = 0
kept_sell    = 0

for _, row in df.iterrows():
    symbol       = row["symbol"]
    buy_rule_id  = int(row["buy_rule_id"])
    sell_rule_id = int(row["sell_rule_id"])

    buy_gtt  = gtt_map.get(buy_rule_id)
    sell_gtt = gtt_map.get(sell_rule_id)

    buy_status  = buy_gtt.get("status",  "NOT FOUND") if buy_gtt  else "NOT FOUND"
    sell_status = sell_gtt.get("status", "NOT FOUND") if sell_gtt else "NOT FOUND"

    # BUY TRIGGERED → keep SELL
    if buy_status == "TRIGGERED":
        kept_sell += 1
        results.append({
            "Symbol": symbol, "BUY Status": buy_status,
            "SELL Status": sell_status, "Action": "✅ Kept",
            "Result": "SELL GTT kept"
        })
        continue

    # BUY NOT TRIGGERED → delete both
    buy_result  = cancel(buy_rule_id,  buy_gtt);  time.sleep(0.1)
    sell_result = cancel(sell_rule_id, sell_gtt); time.sleep(0.1)

    if buy_result  == "Deleted": deleted_buy  += 1
    if sell_result == "Deleted": deleted_sell += 1

    results.append({
        "Symbol": symbol, "BUY Status": buy_status,
        "SELL Status": sell_status, "Action": "🗑️ Deleted",
        "Result": f"BUY: {buy_result} | SELL: {sell_result}"
    })

#===================#
# PRINT RESULTS     #
#===================#
print("\n")
print(pd.DataFrame(results).to_string(index=False))
print("\n")
print("="*70)
print("📊 CLEANUP SUMMARY")
print("="*70)
print(f"📋 Total Stocks Processed : {len(df)}")
print(f"✅ BUY GTTs Deleted       : {deleted_buy}")
print(f"✅ SELL GTTs Deleted      : {deleted_sell}")
print(f"💚 SELL GTTs Kept         : {kept_sell}  (BUY was TRIGGERED)")
print(f"⏰ Completed at           : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*70)
print("\n🎉 Housekeeping Complete!")
