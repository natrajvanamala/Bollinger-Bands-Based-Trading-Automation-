#=========#
# IMPORTS #
#=========#
import os
import time
import logging
import requests
import subprocess
import pandas as pd
from login import login
from datetime import datetime, timedelta

# Suppress Angel One internal logs
logging.getLogger("SmartApi").setLevel(logging.CRITICAL)

#================#
# Login Function #
#================#
angel = login()

#========#
# CONFIG #
#========#
def find_universe_file():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, "symbols.csv")
    if os.path.exists(file_path):
        return file_path
    raise FileNotFoundError("symbols.csv not found in script directory!")

SYMBOLS_CSV   = find_universe_file()
BB_PERIOD     = 20
BB_STD        = 2
SLEEP_TIME    = 0.1       # Delay between API calls (seconds)
POLL_INTERVAL = 5         # How often to re-check LTP (seconds)
ORDER_QTY     = 1         # Quantity per market order
MARKET_END    = "15:30"   # Script auto-exits at this time
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
SUMMARY_CSV   = os.path.join(SCRIPT_DIR, "summary.csv")
ORDER_LOG_CSV = os.path.join(SCRIPT_DIR, "ltp_orders.csv")
VENV_PYTHON   = os.path.join(SCRIPT_DIR, "venv", "bin", "python")

#======================#
# LOAD SYMBOL UNIVERSE #
#======================#
nifty         = pd.read_csv(SYMBOLS_CSV, encoding="utf-8-sig", comment="#")
nifty_symbols = set(nifty["Symbol"].str.upper())

#====================#
# FETCH ANGEL MASTER #
#====================#
url = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
response = requests.get(url)
response.raise_for_status()
instruments = response.json()

def get_universe():
    universe = []
    for inst in instruments:
        if inst.get("exch_seg") != "NSE":
            continue
        angel_symbol = inst.get("symbol", "")
        base_symbol  = angel_symbol.split("-")[0].upper()
        if base_symbol in nifty_symbols:
            universe.append({
                "symbol":       base_symbol,
                "angel_symbol": angel_symbol,
                "token":        inst["token"]
            })
    return pd.DataFrame(universe)

df_universe = get_universe()

print("=" * 70)
print("📈 BOLLINGER BAND — LTP-BASED MARKET ORDER TRADING")
print(f"⏰ Started  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"📂 Universe : {os.path.basename(SYMBOLS_CSV)}  ({len(df_universe)} stocks)")
print(f"🔄 Poll every {POLL_INTERVAL}s | BB({BB_PERIOD}, {BB_STD}) | Auto-exit at {MARKET_END}")
print("=" * 70)

#==================================#
# FETCH OHLC (PAST BB_PERIOD DAYS) #
#==================================#
def fetch_ohlc(token, angel_symbol):
    to_date   = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d 15:30")
    from_date = (datetime.now() - timedelta(days=22)).strftime("%Y-%m-%d 09:15")

    params = {
        "exchange":    "NSE",
        "symboltoken": str(token),
        "interval":    "ONE_DAY",
        "fromdate":    from_date,
        "todate":      to_date
    }

    try:
        data = angel.getCandleData(params)
        if not data.get("status") or not data.get("data"):
            return None

        df = pd.DataFrame(
            data["data"],
            columns=["time", "open", "high", "low", "close", "volume"]
        )

        if len(df) < BB_PERIOD:
            return None

        return df.tail(BB_PERIOD)

    except Exception:
        return None

#=====================#
# BOLLINGER BAND CALC #
#=====================#
def calculate_bb(df):
    df = df.copy()
    df["sma"]      = df["close"].rolling(BB_PERIOD).mean()
    df["std"]      = df["close"].rolling(BB_PERIOD).std()
    df["upper_bb"] = df["sma"] + (BB_STD * df["std"])
    df["lower_bb"] = df["sma"] - (BB_STD * df["std"])
    return df

#=============#
# FETCH LTP   #
#=============#
def fetch_ltp(token, symbol):
    try:
        data = angel.ltpData("NSE", symbol, str(token))
        if data.get("status") and data.get("data"):
            return float(data["data"]["ltp"])
    except Exception:
        pass
    return None

#=====================#
# PLACE MARKET ORDER  #
#=====================#
def place_market_order(symbol, token, side):
    payload = {
        "variety":         "NORMAL",
        "tradingsymbol":   symbol,
        "symboltoken":     str(token),
        "transactiontype": side,
        "exchange":        "NSE",
        "ordertype":       "MARKET",
        "producttype":     "DELIVERY",
        "duration":        "DAY",
        "price":           "0",
        "squareoff":       "0",
        "stoploss":        "0",
        "quantity":        str(ORDER_QTY)
    }

    result = { "order_id": None, "order_response": None }

    try:
        resp = angel.placeOrder(payload)

        if isinstance(resp, dict):
            result["order_response"] = resp.get("message") or (
                "SUCCESS" if resp.get("status") else "FAILED"
            )
            if resp.get("status") and resp.get("data"):
                result["order_id"] = resp["data"].get("orderid")

        elif isinstance(resp, str):
            result["order_id"]       = resp
            result["order_response"] = "SUCCESS"

    except Exception as e:
        result["order_response"] = str(e)

    return result

#=======================#
# SEND EMAIL (helper)   #
#=======================#
def send_email(mode, subject, *extra_args):
    """
    Wrapper around send_email.py subprocess call.
    Always uses absolute paths and cwd=SCRIPT_DIR.
    Logs full stdout/stderr on failure.
    """
    cmd = [VENV_PYTHON, os.path.join(SCRIPT_DIR, "send_email.py"), mode] + list(extra_args) + [subject]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            cwd=SCRIPT_DIR       # ensures relative file refs inside send_email.py resolve correctly
        )
        print(f"📧 Email sent ({mode})!")
        if result.stdout.strip():
            print(f"   {result.stdout.strip()}")

    except subprocess.CalledProcessError as e:
        print(f"⚠️  Email FAILED ({mode}) — exit code {e.returncode}")
        if e.stdout.strip():
            print(f"   STDOUT : {e.stdout.strip()}")
        if e.stderr.strip():
            print(f"   STDERR : {e.stderr.strip()}")   # ← real error will show here

    except Exception as e:
        print(f"⚠️  Email unexpected error ({mode}): {type(e).__name__}: {e}")

#===============================#
# STEP 1 — COMPUTE BB FOR ALL  #
#===============================#
print("\n⏳ Computing Bollinger Bands for all symbols...\n")

bb_data = {}
skipped = []
symbol_order = []

for _, row in df_universe.iterrows():
    df = fetch_ohlc(row["token"], row["angel_symbol"])
    time.sleep(SLEEP_TIME)

    if df is None:
        skipped.append(row["symbol"])
        continue

    df     = calculate_bb(df)
    latest = df.iloc[-1]

    if pd.isna(latest["lower_bb"]) or pd.isna(latest["upper_bb"]):
        skipped.append(row["symbol"])
        continue

    bb_data[row["symbol"]] = {
        "angel_symbol": row["angel_symbol"],
        "token":        row["token"],
        "lower_bb":     round(float(latest["lower_bb"]), 2),
        "upper_bb":     round(float(latest["upper_bb"]), 2),
    }
    symbol_order.append(row["symbol"])

print(f"✅ BB computed for {len(bb_data)} symbols")
if skipped:
    print(f"⚠️  Skipped {len(skipped)}: {', '.join(skipped)}")

print("\n" + "-" * 60)
print(f"{'Symbol':<15} {'Lower BB':>12} {'Upper BB':>12}")
print("-" * 60)
for sym in symbol_order:
    v = bb_data[sym]
    print(f"{sym:<15} {v['lower_bb']:>12.2f} {v['upper_bb']:>12.2f}")
print("-" * 60)

#=======================================#
# SAVE SUMMARY.CSV                      #
#=======================================#
summary_rows = []
for sym in symbol_order:
    v          = bb_data[sym]
    lower      = v["lower_bb"]
    upper      = v["upper_bb"]
    profit     = round(upper - lower, 2)
    profit_pct = round((upper - lower) / lower * 100, 2)
    summary_rows.append({
        "symbol":     sym,
        "lower_band": lower,
        "upper_band": upper,
        "profit":     profit,
        "profit_%":   profit_pct
    })

df_summary = pd.DataFrame(summary_rows).sort_values("symbol").reset_index(drop=True)
df_summary.to_csv(SUMMARY_CSV, index=False)
print(f"\n📁 Summary saved → {SUMMARY_CSV}  ({len(df_summary)} stocks)")

#================================#
# PRE-MARKET EMAIL               #
#================================#
today   = datetime.now().strftime("%Y-%m-%d")
subject = f"📊 BB Pre-Market {today} — {len(df_summary)} Stocks"
send_email("pre", subject, SUMMARY_CSV)

#=======================================#
# STEP 2 — LTP MONITORING + ORDER LOGIC #
#=======================================#
ordered = {sym: None for sym in bb_data}

if not os.path.exists(ORDER_LOG_CSV):
    pd.DataFrame(columns=[
        "time", "symbol", "side",
        "lower_bb", "upper_bb", "band_diff",
        "order_id", "order_response"
    ]).to_csv(ORDER_LOG_CSV, index=False)

print(f"\n🔄 LTP monitor started — auto-exits at {MARKET_END} | Ctrl+C to stop early\n")
print("=" * 70)

try:
    while True:

        if datetime.now().strftime("%H:%M") >= MARKET_END:
            print(f"\n⏰ Market closed ({MARKET_END}). Auto-exiting.\n")
            break

        cycle_time   = datetime.now().strftime("%H:%M:%S")
        active_count = sum(1 for v in ordered.values() if v is None)

        if active_count == 0:
            print(f"\n🎉 All symbols triggered. Exiting monitor.")
            break

        print(f"[{cycle_time}] Active: {active_count} symbols | Auto-exit at {MARKET_END}")

        for sym in symbol_order:
            meta = bb_data[sym]

            if ordered[sym] is not None:
                continue

            ltp = fetch_ltp(meta["token"], meta["angel_symbol"])
            time.sleep(SLEEP_TIME)

            if ltp is None:
                print(f"  ⚠️  {sym:<15} — LTP unavailable")
                continue

            lower = meta["lower_bb"]
            upper = meta["upper_bb"]
            side  = None

            if ltp <= lower:
                side = "BUY"
                print(f"  🟢 {sym:<15} LTP {ltp:>10.2f} <= LowerBB {lower:>10.2f}  → BUY MARKET")

            elif ltp >= upper:
                side = "SELL"
                print(f"  🔴 {sym:<15} LTP {ltp:>10.2f} >= UpperBB {upper:>10.2f}  → SELL MARKET")

            if side:
                res       = place_market_order(meta["angel_symbol"], meta["token"], side)
                band_diff = round(upper - lower, 2)

                if res["order_id"]:
                    print(f"      ✅ {side} placed       | order_id   : {res['order_id']}")
                    print(f"      📋 Response          | {res['order_response']}")
                    ordered[sym] = f"{side}_PLACED"
                else:
                    print(f"      ❌ {side} FAILED for {sym} | {res['order_response']}")
                    ordered[sym] = f"{side}_FAILED"

                new_row = {
                    "time":           cycle_time,
                    "symbol":         sym,
                    "side":           side,
                    "lower_bb":       lower,
                    "upper_bb":       upper,
                    "band_diff":      band_diff,
                    "order_id":       res["order_id"] or "N/A",
                    "order_response": res["order_response"]
                }
                pd.DataFrame([new_row]).to_csv(
                    ORDER_LOG_CSV, mode="a", header=False, index=False
                )
                print(f"      💾 Saved to {ORDER_LOG_CSV}")

        print(f"  💤 Sleeping {POLL_INTERVAL}s...\n")
        time.sleep(POLL_INTERVAL)

except KeyboardInterrupt:
    print("\n\n🛑 Monitor stopped manually (Ctrl+C)\n")

#===============#
# FINAL SUMMARY #
#===============#
print("=" * 70)
print("📊 SESSION SUMMARY")
print("=" * 70)

if os.path.exists(ORDER_LOG_CSV):
    df_log = pd.read_csv(ORDER_LOG_CSV)

    if not df_log.empty:
        buy_count  = len(df_log[df_log["side"] == "BUY"])
        sell_count = len(df_log[df_log["side"] == "SELL"])
        failed     = len(df_log[df_log["order_response"].str.upper() != "SUCCESS"])

        print(df_log.to_string(index=False))
        print()
        print(f"🟢 BUY  orders  : {buy_count}")
        print(f"🔴 SELL orders  : {sell_count}")
        print(f"❌ Failed       : {failed}")
        print(f"📁 Saved to     : {ORDER_LOG_CSV}")
    else:
        print("ℹ️  No orders were triggered during this session.")
        df_log = pd.DataFrame()
else:
    print("ℹ️  No orders were triggered during this session.")
    df_log = pd.DataFrame()

no_trigger = [sym for sym, state in ordered.items() if state is None]
if no_trigger:
    print(f"\n⬜ No trigger for {len(no_trigger)} symbols: {', '.join(no_trigger)}")

print(f"\n⏰ Completed at : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

#================================#
# POST-MARKET EMAIL              #
#================================#
today   = datetime.now().strftime("%Y-%m-%d")
subject = f"📊 BB Post-Market {today} — {len(df_log)} Orders Triggered"
send_email("post", subject, SUMMARY_CSV, ORDER_LOG_CSV)
