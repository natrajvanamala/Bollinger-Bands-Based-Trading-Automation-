#!/usr/bin/env python3

# ========= #
# IMPORTS   #
# ========= #
import json
import pandas as pd
from login import login

# ========= #
# LOGIN     #
# ========= #
angel = login()

if not angel:
    print("❌ Login failed")
    exit()

print("=" * 80)
print("📋 FETCHING ALL GTT ORDERS")
print("=" * 80)

# ============================= #
# FIX SMARTAPI RESPONSE BUG     #
# ============================= #
original_request = angel._request

def patched_request(route, method, params=None):
    try:
        return original_request(route, method, params)
    except KeyError as e:
        if str(e) == "'message'":
            return {"status": True, "data": []}
        raise

angel._request = patched_request

# ============================= #
# FETCH ALL GTT RULES           #
# ============================= #
try:
    response = angel.gttLists(["FORALL"], 1, 5000)

    # Convert string response if needed
    if isinstance(response, str):
        response = json.loads(response)

    # Extract data safely
    if isinstance(response, dict):
        all_gtts = response.get("data", [])
    elif isinstance(response, list):
        all_gtts = response
    else:
        all_gtts = []

    print(f"\n✅ Found {len(all_gtts)} GTT Orders\n")

    if len(all_gtts) == 0:
        print("No GTTs found in account.")
        exit()

    # ============================= #
    # CONVERT TO TABULAR FORMAT     #
    # ============================= #
    table_data = []

    for gtt in all_gtts:
        table_data.append({
            "ID": gtt.get("id"),
            "Symbol": gtt.get("tradingsymbol"),
            "Type": gtt.get("transactiontype"),
            "Price": gtt.get("price"),
            "Trigger Price": gtt.get("triggerprice"),
            "Qty": gtt.get("qty"),
            "Status": gtt.get("status"),
            "Exchange": gtt.get("exchange"),
            "Token": gtt.get("symboltoken"),
            "Created Date": gtt.get("createddate")
        })

    df = pd.DataFrame(table_data)

    # Optional: Sort by Symbol
    df = df.sort_values(by="Symbol")

    print("=" * 120)
    print("📊 GTT ORDERS TABLE")
    print("=" * 120)
    print(df.to_string(index=False))
    print("=" * 120)

    print(f"\n📌 Total GTT Orders: {len(df)}")

    # ============================= #
    # SAVE CSV (OPTIONAL BUT USEFUL)
    # ============================= #
    df.to_csv("get_all_gtt_tabular.csv", index=False)
    print("📁 Saved as get_all_gtt_tabular.csv")

except Exception as e:
    print(f"❌ Error occurred: {e}")
    import traceback
    traceback.print_exc()
