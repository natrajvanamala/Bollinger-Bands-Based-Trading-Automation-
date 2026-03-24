#=========#
# IMPORTS #
#=========#
import os
import time
import glob
import requests
import pandas as pd
from login import login
from datetime import datetime, timedelta

#================#
# Login Function #
#================#
angel = login()

#========#
# CONFIG #
#========#
# Auto-discover universe file from current working directory
def find_universe_file(directory="."):
    matches = glob.glob(os.path.join(directory, "*.csv"))
    universe_files = [f for f in matches if "universe" in os.path.basename(f).lower()]
    if universe_files:
        return universe_files[0]
    raise FileNotFoundError("No universe CSV found! File must contain 'universe' in its name.")

SYMBOLS_CSV = find_universe_file()
BB_PERIOD = 20
BB_STD = 2
SLEEP_TIME = 0.1

#======================#
# LOAD SYMBOL UNIVERSE #
#======================#
nifty = pd.read_csv(SYMBOLS_CSV)
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
        base_symbol = angel_symbol.split("-")[0].upper()

        if base_symbol in nifty_symbols:
            universe.append({
                "symbol": base_symbol,
                "angel_symbol": angel_symbol,
                "token": inst["token"]
            })

    return pd.DataFrame(universe)

df_universe = get_universe()

print(f"✅ Universe loaded: {len(df_universe)} stocks")

#================================#
# FETCH OHLC (PAST 20 DAYS ONLY) #
#================================#

def fetch_ohlc(token, angel_symbol):
    to_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d 15:30")
    from_date = (datetime.now() - timedelta(days=41)).strftime("%Y-%m-%d 09:15")

    params = {
        "exchange": "NSE",
        "symboltoken": str(token),
        "interval": "ONE_DAY",
        "fromdate": from_date,
        "todate": to_date
    }

    try:
        data = angel.getCandleData(params)
        #print(f"📊 OHLC RAW RESPONSE for Symbol :- {angel_symbol} | Token :- {token}: {data}")

        if not data.get("status"):
            print(f"❌ OHLC status failed for Symbol :- {angel_symbol} | Token :- {token}: {data}")
            return None
        if not data.get("data"):
            print(f"❌ OHLC empty data for Symbol :- {angel_symbol} | Token :- {token}: {data}")
            return None

        df = pd.DataFrame(
            data["data"],
            columns=["time", "open", "high", "low", "close", "volume"]
        )

        #print(f"✅ OHLC rows total fetched: {len(df)}")

        if len(df) < BB_PERIOD:
            print(f"⚠️ Skipping {angel_symbol} token {token} | Only {len(df)} candles")
            return None

        return df.tail(BB_PERIOD)

    except Exception as e:
        print(f"⚠️ Candle fetch failed for token {token}: {e}")
        return None

#=====================#
# BOLLINGER BAND CALC #
#=====================#
def calculate_bb(df):
    df["sma"] = df["close"].rolling(BB_PERIOD).mean()
    df["std"] = df["close"].rolling(BB_PERIOD).std()
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
        "exchange": "NSE",
        "tradingsymbol": symbol,
        "symboltoken": str(token),
        "transactiontype": side,
        "producttype": "DELIVERY",
        "price": str(price),
        "triggerprice": str(price),
        "qty": "1",
        "disclosedqty": "0",
        "ruleType": "SINGLE"
    }

    response = angel.gttCreateRule(payload)

    print(f"GTT RESPONSE | {symbol} | {side} | {response}")

    # Angel sometimes returns rule_id as int
    if isinstance(response, int):
        print(f"✅ GTT CREATED | {symbol} | {side} | Rule ID {response}")
        return response

    # Sometimes returns dict with status
    if isinstance(response, dict):
        if response.get("status") and response.get("data"):
            rule_id = response["data"].get("id")
            print(f"✅ GTT CREATED | {symbol} | {side} | Rule ID {rule_id}")
            return rule_id

    print(f"❌ GTT Failed | {symbol} | {side}")
    return None

#================#
# MAIN EXECUTION #
#================#
results = []

for _, row in df_universe.iterrows():
    print(f"\n🔄 Processing {row['symbol']} | Token {row['token']}")
    
    df = fetch_ohlc(row["token"], row["angel_symbol"])
    time.sleep(SLEEP_TIME)

    if df is None:
        print("⚠️ OHLC DF is None, skipping")
        continue
    print(f"✅ OHLC rows fetched: {len(df)}")

    df = calculate_bb(df)
    latest = df.iloc[-1]

    lower_bb = latest["lower_bb"]
    upper_bb = latest["upper_bb"]
    
    buy_rule_id = place_gtt(row["symbol"], row["token"], "BUY", lower_bb)
    sell_rule_id = place_gtt(row["symbol"], row["token"], "SELL", upper_bb)

    if buy_rule_id or sell_rule_id:
        results.append({
            "symbol": row["symbol"],
            "angel_symbol": row["angel_symbol"],
            "token": row["token"],
            "lower_bb": round_price(lower_bb),
            "upper_bb": round_price(upper_bb),
            "buy_rule_id": buy_rule_id,
            "sell_rule_id": sell_rule_id
            })

#===============#
# SAVE SNAPSHOT #
#===============#
df_results = pd.DataFrame(results)
df_results.to_csv("output.csv", index=True)

print("✅ GTT Placed")
