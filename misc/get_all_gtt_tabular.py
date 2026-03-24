#!/usr/bin/env python3
# ========= #
# IMPORTS   #
# ========= #
import json
import math
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
        response = original_request(route, method, params)

        if response is None:
            print(f"⚠️  Warning: Empty response for route '{route}', returning default.")
            return {"status": True, "message": "No data", "data": []}

        if isinstance(response, dict) and "message" not in response:
            response["message"] = "No message provided"

        return response

    except KeyError as e:
        print(f"⚠️  KeyError caught in _request for route '{route}': {e}")
        return {"status": True, "message": "KeyError suppressed", "data": []}

    except Exception as e:
        print(f"❌ Unexpected error in _request for route '{route}': {e}")
        raise

angel._request = patched_request

# ============================= #
# FETCH ALL GTT RULES (PAGINATE)#
# ============================= #
try:
    all_gtts = []
    page      = 1
    page_size = 500

    while True:
        response = angel.gttLists(["FORALL"], page, page_size)

        if isinstance(response, str):
            response = json.loads(response)

        if isinstance(response, dict):
            batch = response.get("data", [])
        elif isinstance(response, list):
            batch = response
        else:
            batch = []

        if not batch:
            break

        all_gtts.extend(batch)
        print(f"   📄 Page {page}: fetched {len(batch)} orders (total so far: {len(all_gtts)})")

        if len(batch) < page_size:
            break
        page += 1

    print(f"\n✅ Total GTT Orders Fetched (raw): {len(all_gtts)}\n")

    if len(all_gtts) == 0:
        print("No GTTs found in account.")
        exit()

    # ============================= #
    # CONVERT TO TABULAR FORMAT     #
    # ============================= #
    table_data = []
    for gtt in all_gtts:
        table_data.append({
            "ID":           gtt.get("id"),
            "Symbol":       gtt.get("tradingsymbol"),
            "Type":         gtt.get("transactiontype"),
            "Price":        gtt.get("price"),
            "Trigger Price":gtt.get("triggerprice"),
            "Qty":          gtt.get("qty"),
            "Status":       gtt.get("status"),
            "Exchange":     gtt.get("exchange"),
            "Token":        gtt.get("symboltoken"),
            "Created Date": gtt.get("createddate")
        })

    df_all = pd.DataFrame(table_data)

    # ============================= #
    # NORMALISE STATUS COLUMN       #
    # ============================= #
    # Replace NaN / None / blank with "UNKNOWN"
    df_all["Status"] = df_all["Status"].fillna("UNKNOWN").replace("", "UNKNOWN").str.upper().str.strip()

    # ============================= #
    # STATUS SUMMARY (all GTTs)     #
    # ============================= #
    print("=" * 60)
    print("📊 STATUS SUMMARY (ALL FETCHED GTTs)")
    print("=" * 60)

    status_counts = df_all["Status"].value_counts()
    for status, count in status_counts.items():
        emoji = "✅" if status == "NEW" else "❌" if status == "CANCELLED" else "ℹ️"
        print(f"   {emoji}  {status:<20} : {count}")

    print("-" * 60)
    print(f"   📌  {'TOTAL':<20} : {len(df_all)}")
    print("=" * 60)

    # ============================= #
    # FILTER — KEEP ONLY ACTIVE GTTs#
    # ============================= #
    EXCLUDED_STATUSES = ["CANCELLED", "UNKNOWN"]
    df_active = df_all[~df_all["Status"].isin(EXCLUDED_STATUSES)].copy()
    df_active = df_active.sort_values(by="Symbol").reset_index(drop=True)

    # ============================= #
    # DISPLAY ACTIVE GTTs           #
    # ============================= #
    print("\n")
    print("=" * 120)
    print("📊 ACTIVE GTT ORDERS (Cancelled & Unknown excluded)")
    print("=" * 120)
    print(df_active.to_string(index=False))
    print("=" * 120)

    # ============================= #
    # FINAL SUMMARY                 #
    # ============================= #
    print("\n")
    print("=" * 60)
    print("📌 FINAL SUMMARY")
    print("=" * 60)
    for status, count in status_counts.items():
        emoji = "✅" if status == "NEW" else "❌" if status == "CANCELLED" else "ℹ️"
        print(f"   {emoji}  {status:<20} : {count}")
    print("-" * 60)
    print(f"   ✅  {'ACTIVE (saved)':<20} : {len(df_active)}")
    print(f"   📦  {'TOTAL FETCHED':<20} : {len(df_all)}")
    print("=" * 60)

    # ============================= #
    # SAVE ONLY ACTIVE GTTs         #
    # ============================= #
    df_active.to_csv("get_all_gtt_tabular.csv", index=False)
    print("\n📁 Saved active GTTs to → get_all_gtt_tabular.csv")

except Exception as e:
    print(f"❌ Error occurred: {e}")
    import traceback
    traceback.print_exc()
