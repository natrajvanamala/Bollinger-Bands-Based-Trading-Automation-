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
print("🧹 GTT CLEANUP - SMART DELETION BASED ON TRIGGER STATUS")
print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*70)

#========#
# CONFIG #
#========#
SLEEP_TIME = 0.5

#=====================#
# READ OUTPUT.CSV     #
#=====================#
print("\n📂 Reading output.csv...")

try:
    df = pd.read_csv("output.csv")
    print(f"✅ Loaded {len(df)} stocks from output.csv\n")
except FileNotFoundError:
    print("❌ output.csv not found!")
    print("💡 Make sure you ran main.py first to create output.csv")
    exit()

if df.empty:
    print("❌ output.csv is empty!")
    exit()

print(f"📊 Columns: {', '.join(df.columns.tolist())}")
print(f"📋 Sample stocks: {', '.join(df['symbol'].head(5).tolist())}...\n")

#=====================#
# FETCH ALL GTT RULES #
#=====================#
print("📥 Fetching all GTT rules from Angel One...")

# Monkey-patch to handle SmartAPI library bug
original_request = angel._request

def patched_request(route, method, params=None):
    try:
        return original_request(route, method, params)
    except KeyError as e:
        if str(e) == "'message'":
            return {"status": True, "data": []}
        raise

angel._request = patched_request

try:
    response = angel.gttLists(["FORALL"], 1, 500)
    
    if isinstance(response, str):
        response = json.loads(response)
    
    if isinstance(response, dict):
        all_gtts = response.get("data", [])
    elif isinstance(response, list):
        all_gtts = response
    else:
        all_gtts = []
    
    print(f"✅ Found {len(all_gtts)} total GTT rules in your account\n")
    
except Exception as e:
    print(f"❌ Error fetching GTTs: {e}")
    exit()

#================================#
# BUILD GTT STATUS MAP BY RULE ID #
#================================#
print("🔍 Building GTT status map...")

# Map: rule_id -> {status, symboltoken, exchange, ...}
gtt_map = {}

for gtt in all_gtts:
    rule_id = gtt.get("id")
    if rule_id:
        gtt_map[int(rule_id)] = gtt

print(f"✅ Mapped {len(gtt_map)} GTT rules by ID\n")

#================================#
# PROCESS EACH STOCK             #
#================================#
print("="*70)
print("🔍 PROCESSING STOCKS FROM OUTPUT.CSV")
print("="*70)

deleted_buy = 0
deleted_sell = 0
kept_sell = 0
skipped_already_cancelled = 0
missing_buy = 0
missing_sell = 0

# Store results for table
results = []

for idx, row in df.iterrows():
    symbol = row["symbol"]
    buy_rule_id = int(row["buy_rule_id"])
    sell_rule_id = int(row["sell_rule_id"])
    
    # Get BUY GTT info
    buy_gtt = gtt_map.get(buy_rule_id)
    
    if not buy_gtt:
        results.append({
            "Symbol": symbol,
            "BUY Status": "NOT FOUND",
            "SELL Status": "N/A",
            "Action": "⚠️ Missing",
            "Result": "BUY not found"
        })
        missing_buy += 1
        continue
    
    buy_status = buy_gtt.get("status")
    
    # Check if status is None or missing
    if buy_status is None or buy_status == "":
        results.append({
            "Symbol": symbol,
            "BUY Status": "None",
            "SELL Status": "N/A",
            "Action": "⚠️ Skipped",
            "Result": "Status unknown"
        })
        missing_buy += 1
        continue
    
    #================================#
    # CASE 1: BUY TRIGGERED          #
    #================================#
    if buy_status == "TRIGGERED":
        results.append({
            "Symbol": symbol,
            "BUY Status": "TRIGGERED",
            "SELL Status": "ACTIVE",
            "Action": "✅ Kept",
            "Result": "SELL GTT kept"
        })
        kept_sell += 1
        continue
    
    #================================#
    # CASE 2: ALREADY CANCELLED/REJECTED #
    #================================#
    if buy_status in ["CANCELLED", "REJECTED"]:
        sell_gtt = gtt_map.get(sell_rule_id)
        sell_status = sell_gtt.get("status") if sell_gtt else "NOT FOUND"
        
        results.append({
            "Symbol": symbol,
            "BUY Status": buy_status,
            "SELL Status": sell_status,
            "Action": "⏭️ Skipped",
            "Result": "Already cancelled"
        })
        skipped_already_cancelled += 1
        continue
    
    #================================#
    # CASE 3: BUY NOT TRIGGERED      #
    # → Delete BOTH BUY and SELL     #
    #================================#
    
    buy_delete_status = "Failed"
    sell_delete_status = "Failed"
    
    # Delete BUY GTT
    try:
        buy_payload = {
            "id": str(buy_rule_id),
            "symboltoken": str(buy_gtt.get("symboltoken")),
            "exchange": str(buy_gtt.get("exchange"))
        }
        
        response = angel.gttCancelRule(buy_payload)
        
        if isinstance(response, dict):
            if response.get("status"):
                buy_delete_status = "Deleted"
                deleted_buy += 1
            elif response.get("errorcode") == "AB9028":
                buy_delete_status = "Already removed"
            else:
                buy_delete_status = f"Failed: {response.get('message', 'Unknown')}"
        
        time.sleep(SLEEP_TIME)
        
    except Exception as e:
        if "Order not found" in str(e) or "AB9028" in str(e):
            buy_delete_status = "Already removed"
        else:
            buy_delete_status = f"Error: {str(e)[:20]}"
    
    # Delete SELL GTT
    sell_gtt = gtt_map.get(sell_rule_id)
    
    if sell_gtt:
        try:
            sell_payload = {
                "id": str(sell_rule_id),
                "symboltoken": str(sell_gtt.get("symboltoken")),
                "exchange": str(sell_gtt.get("exchange"))
            }
            
            response = angel.gttCancelRule(sell_payload)
            
            if isinstance(response, dict):
                if response.get("status"):
                    sell_delete_status = "Deleted"
                    deleted_sell += 1
                elif response.get("errorcode") == "AB9028":
                    sell_delete_status = "Already removed"
                else:
                    sell_delete_status = f"Failed: {response.get('message', 'Unknown')}"
            
            time.sleep(SLEEP_TIME)
            
        except Exception as e:
            if "Order not found" in str(e) or "AB9028" in str(e):
                sell_delete_status = "Already removed"
            else:
                sell_delete_status = f"Error: {str(e)[:20]}"
    else:
        sell_delete_status = "Not found"
        missing_sell += 1
    
    results.append({
        "Symbol": symbol,
        "BUY Status": buy_status,
        "SELL Status": sell_gtt.get("status") if sell_gtt else "N/A",
        "Action": "🗑️ Deleted",
        "Result": f"BUY: {buy_delete_status}, SELL: {sell_delete_status}"
    })

# Display results in table
print("\n")
results_df = pd.DataFrame(results)
print(results_df.to_string(index=False))
print("\n")

#===============#
# FINAL SUMMARY #
#===============#
print("\n" + "="*70)
print("📊 CLEANUP SUMMARY")
print("="*70)
print(f"📋 Total stocks processed: {len(df)}")
print(f"✅ BUY GTTs deleted: {deleted_buy}")
print(f"✅ SELL GTTs deleted: {deleted_sell}")
print(f"💚 SELL GTTs kept (BUY triggered): {kept_sell}")
print(f"⏭️  Already cancelled (skipped): {skipped_already_cancelled}")
print(f"⚠️  BUY GTTs not found: {missing_buy}")
print(f"⚠️  SELL GTTs not found: {missing_sell}")
print(f"⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*70)

if kept_sell > 0:
    print(f"\n💡 {kept_sell} stocks had triggered BUY orders - their SELL GTTs are still active!")

print("\n🎉 GTT Cleanup Complete!")
