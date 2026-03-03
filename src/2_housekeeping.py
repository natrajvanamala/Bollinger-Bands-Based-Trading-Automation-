#=========#
# IMPORTS #
#=========#
import time
import json
import pandas as pd
from datetime import datetime
from login import login

#================#
# Login Function #
#================#
angel = login()

if not angel:
    print("❌ Login failed. Exiting.")
    exit()

print("="*70)
print("🧹 GTT HOUSEKEEPING")
print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*70)

#========#
# CONFIG #
#========#
SLEEP_TIME = 0.1   # 10 req/sec (within Angel One limit)

#====================#
# READ OUTPUT.CSV    #
# Only today's file  #
#====================#
today_str = datetime.now().strftime("%Y-%m-%d")

try:
    df = pd.read_csv("output.csv")
except FileNotFoundError:
    print("❌ output.csv not found! Run 1_main.py first.")
    exit()

if df.empty:
    print("❌ output.csv is empty!")
    exit()

# Verify output.csv was created today
import os
file_mtime = os.path.getmtime("output.csv")
file_date = datetime.fromtimestamp(file_mtime).strftime("%Y-%m-%d")

if file_date != today_str:
    print(f"⚠️  WARNING: output.csv was created on {file_date}, not today ({today_str})")
    confirm = input("Do you still want to proceed? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("❌ Aborted.")
        exit()

print(f"\n📂 Loaded {len(df)} stocks from output.csv (created: {file_date})\n")

#========================#
# FETCH ALL GTT RULES    #
#========================#

# Monkey-patch to handle SmartAPI library bug
original_request = angel._request

def patched_request(route, method, params=None):
    try:
        return original_request(route, method, params)
    except KeyError:
        return {"status": True, "data": []}

angel._request = patched_request

try:
    response = angel.gttLists(["FORALL"], 1, 500)
    if isinstance(response, str):
        response = json.loads(response)
    all_gtts = response.get("data", []) if isinstance(response, dict) else []
except Exception as e:
    print(f"❌ Failed to fetch GTT rules: {e}")
    exit()

# Map rule_id → gtt object
gtt_map = {int(g["id"]): g for g in all_gtts if g.get("id")}

print(f"📥 Fetched {len(gtt_map)} GTT rules from Angel One\n")

#========================#
# HELPER: CANCEL ONE GTT #
#========================#
def cancel_gtt(rule_id, gtt_obj):
    """
    Cancel a single GTT rule.
    Returns a string result: Deleted | Already Removed | Failed | Error
    """
    if not gtt_obj:
        return "Not Found"

    try:
        payload = {
            "id": str(rule_id),
            "symboltoken": str(gtt_obj.get("symboltoken", "")),
            "exchange": str(gtt_obj.get("exchange", ""))
        }

        res = angel.gttCancelRule(payload)

        # Angel returns dict
        if isinstance(res, dict):
            if res.get("status") is True:
                return "Deleted"
            elif res.get("errorcode") == "AB9028":
                return "Already Removed"
            else:
                return f"Failed ({res.get('errorcode', res.get('message', 'Unknown'))})"

        # Unexpected response type
        return "Failed (Unexpected Response)"

    except Exception as e:
        err = str(e)
        if "AB9028" in err or "Order not found" in err:
            return "Already Removed"
        return f"Error ({err[:30]})"

#========================#
# PROCESS EACH STOCK     #
#========================#
results      = []
deleted_buy  = 0
deleted_sell = 0
kept_sell    = 0

print("="*70)
print("🔍 PROCESSING STOCKS")
print("="*70)

for _, row in df.iterrows():

    symbol      = row["symbol"]
    buy_rule_id  = int(row["buy_rule_id"])
    sell_rule_id = int(row["sell_rule_id"])

    buy_gtt  = gtt_map.get(buy_rule_id)
    sell_gtt = gtt_map.get(sell_rule_id)

    buy_status  = buy_gtt.get("status",  "NOT FOUND") if buy_gtt  else "NOT FOUND"
    sell_status = sell_gtt.get("status", "NOT FOUND") if sell_gtt else "NOT FOUND"

    #==============================#
    # CASE 1: BUY TRIGGERED        #
    # → Keep SELL GTT intact       #
    #==============================#
    if buy_status == "TRIGGERED":
        results.append({
            "Symbol"      : symbol,
            "BUY Status"  : buy_status,
            "SELL Status" : sell_status,
            "Action"      : "✅ Kept",
            "Result"      : "SELL GTT kept"
        })
        kept_sell += 1
        continue

    #==============================#
    # CASE 2: BUY NOT TRIGGERED    #
    # → Delete BOTH BUY & SELL     #
    #==============================#
    buy_result  = cancel_gtt(buy_rule_id,  buy_gtt)
    time.sleep(SLEEP_TIME)

    sell_result = cancel_gtt(sell_rule_id, sell_gtt)
    time.sleep(SLEEP_TIME)

    if buy_result  == "Deleted": deleted_buy  += 1
    if sell_result == "Deleted": deleted_sell += 1

    results.append({
        "Symbol"      : symbol,
        "BUY Status"  : buy_status,
        "SELL Status" : sell_status,
        "Action"      : "🗑️ Deleted",
        "Result"      : f"BUY: {buy_result} | SELL: {sell_result}"
    })

#========================#
# PRINT RESULTS TABLE    #
#========================#
print("\n")
results_df = pd.DataFrame(results)
print(results_df.to_string(index=False))
print("\n")

#========================#
# SUMMARY                #
#========================#
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
