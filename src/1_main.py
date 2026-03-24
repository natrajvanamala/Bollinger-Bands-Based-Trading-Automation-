#=========#
# IMPORTS #
#=========#
import os
import time
import glob
import logging
import requests
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
def find_universe_file(directory="."):
    matches = glob.glob(os.path.join(directory, "*.csv"))
    universe_files = [f for f in matches if "universe" in os.path.basename(f).lower()]
    if universe_files:
        return universe_files[0]
    raise FileNotFoundError("No universe CSV found! File must contain 'universe' in its name.")

SYMBOLS_CSV  = find_universe_file()
BB_PERIOD    = 20
BB_STD       = 2
SLEEP_TIME   = 0.1

#======================#
# LOAD SYMBOL UNIVERSE #
#======================#
nifty         = pd.read_csv(SYMBOLS_CSV, encoding="latin1")
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

print("="*70)
print("📈 BOLLINGER BAND GTT PLACEMENT")
print(f"⏰ Started  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"📂 Universe : {os.path.basename(SYMBOLS_CSV)}  ({len(df_universe)} stocks)")
print("="*70)

#================================#
# FETCH OHLC (PAST 20 DAYS ONLY) #
#================================#
def fetch_ohlc(token, angel_symbol):
    to_date   = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d 15:30")
    from_date = (datetime.now() - timedelta(days=41)).strftime("%Y-%m-%d 09:15")

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
    df["sma"]      = df["close"].rolling(BB_PERIOD).mean()
    df["std"]      = df["close"].rolling(BB_PERIOD).std()
    df["upper_bb"] = df["sma"] + (BB_STD * df["std"])
    df["lower_bb"] = df["sma"] - (BB_STD * df["std"])
    return df

#===================#
# ROUND PRICE (INT) #
#===================#
def round_price(price):
    return int(round(float(price)))

#====================#
# PLACE GTT (SINGLE) #
#====================#
def place_gtt(symbol, token, side, price):
    price = round_price(price)

    payload = {
        "exchange":       "NSE",
        "tradingsymbol":  symbol,
        "symboltoken":    str(token),
        "transactiontype": side,
        "producttype":    "DELIVERY",
        "price":          str(price),
        "triggerprice":   str(price),
        "qty":            "1",
        "disclosedqty":   "0",
        "ruleType":       "SINGLE"
    }

    try:
        response = angel.gttCreateRule(payload)

        if isinstance(response, int):
            return response

        if isinstance(response, dict):
            if response.get("status") and response.get("data"):
                return response["data"].get("id")

    except Exception:
        pass

    return None

#================#
# MAIN EXECUTION #
#================#
results       = []
skipped_list  = []   # symbols with insufficient OHLC
failed_list   = []   # symbols where GTT creation failed

for _, row in df_universe.iterrows():

    df = fetch_ohlc(row["token"], row["angel_symbol"])
    time.sleep(SLEEP_TIME)

    if df is None:
        skipped_list.append(row["symbol"])
        continue

    df     = calculate_bb(df)
    latest = df.iloc[-1]

    lower_bb = latest["lower_bb"]
    upper_bb = latest["upper_bb"]

    buy_rule_id  = place_gtt(row["symbol"], row["token"], "BUY",  lower_bb)
    time.sleep(SLEEP_TIME)
    sell_rule_id = place_gtt(row["symbol"], row["token"], "SELL", upper_bb)
    time.sleep(SLEEP_TIME)

    if buy_rule_id and sell_rule_id:
        results.append({
            "symbol":       row["symbol"],
            "angel_symbol": row["angel_symbol"],
            "token":        row["token"],
            "lower_bb":     round_price(lower_bb),
            "upper_bb":     round_price(upper_bb),
            "buy_rule_id":  buy_rule_id,
            "sell_rule_id": sell_rule_id
        })
    else:
        failed_list.append(row["symbol"])

#===============#
# SAVE SNAPSHOT #
#===============#
df_results = pd.DataFrame(results)
df_results.to_csv("output.csv", index=True)

#================#
# PRINT RESULTS  #
#================#
print("\n")

if not df_results.empty:
    display_df = df_results[["symbol", "lower_bb", "upper_bb", "buy_rule_id", "sell_rule_id"]].copy()
    display_df.columns = ["Symbol", "BUY Price", "SELL Price", "BUY Rule ID", "SELL Rule ID"]
    print(display_df.to_string(index=False))

print("\n")
print("="*70)
print("📊 SUMMARY")
print("="*70)
print(f"✅ GTTs Placed   : {len(results)}")
print(f"⚠️  Skipped       : {len(skipped_list)}  (insufficient OHLC data)")
if skipped_list:
    print(f"   Symbols       : {', '.join(skipped_list)}")
print(f"❌ Failed        : {len(failed_list)}  (GTT creation error)")
if failed_list:
    print(f"   Symbols       : {', '.join(failed_list)}")
print(f"⏰ Completed at  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*70)
