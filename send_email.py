# ================================================================
# send_email.py
#
# Usage:
#   Pre-market:
#     python send_email.py pre summary.csv "Subject"
#
#   Post-market:
#     python send_email.py post summary.csv ltp_orders.csv "Subject"
# ================================================================

import smtplib
import os
import sys
import pandas as pd
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
from datetime import datetime

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

SENDER   = "natrajvanamalapro@gmail.com"
RECEIVER = "natrajvanamalapro@gmail.com"

# ================================================================
# HTML STYLING
# ================================================================
TABLE_STYLE = """
<style>
    body  { font-family: Arial, sans-serif; font-size: 13px; color: #222; }
    h2    { color: #2c3e50; border-bottom: 2px solid #2c3e50; padding-bottom: 6px; }
    p     { color: #444; }
    table {
        border-collapse: collapse;
        width: 100%;
        margin-top: 10px;
    }
    th {
        background-color: #2c3e50;
        color: white;
        padding: 9px 14px;
        text-align: center;
        font-size: 13px;
        white-space: nowrap;
    }
    td {
        padding: 7px 14px;
        text-align: center;
        border: 1px solid #ddd;
        white-space: nowrap;
    }
    tr:nth-child(even) { background-color: #f7f7f7; }
    tr:hover           { background-color: #eaf4fb; }
    .footer { margin-top: 24px; font-size: 11px; color: #aaa; }
</style>
"""

# ================================================================
# PRE-MARKET TABLE
# Columns: Symbol | Lower BB | Upper BB | Profit (₹) | Percentage
# Sorted alphabetically by symbol
# Percentage shown as "6.25%"
# ================================================================
def render_pre_market_table(df):
    df = df.sort_values("symbol").reset_index(drop=True)
    rows = ""
    for _, r in df.iterrows():
        rows += f"""
        <tr>
            <td><b>{r['symbol']}</b></td>
            <td>{float(r['lower_band']):.2f}</td>
            <td>{float(r['upper_band']):.2f}</td>
            <td>{float(r['profit']):.2f}</td>
            <td>{float(r['profit_%']):.2f}%</td>
        </tr>"""

    return f"""
    <table>
        <tr>
            <th>Symbol</th>
            <th>Lower BB</th>
            <th>Upper BB</th>
            <th>Profit (₹)</th>
            <th>Percentage</th>
        </tr>
        {rows}
    </table>"""

# ================================================================
# POST-MARKET TABLE
# Same alphabetical order as pre-market
# lower_bb column → ✅ if BUY placed, ❌ if no activity
# upper_bb column → ✅ if SELL placed, ❌ if no activity
# time / order_id / order_response → filled if order placed, blank if not
# ================================================================
def render_post_market_table(df_summary, df_orders):
    df_summary = df_summary.sort_values("symbol").reset_index(drop=True)

    # Build a quick lookup: symbol → order row
    order_map = {}
    if not df_orders.empty:
        for _, o in df_orders.iterrows():
            order_map[o["symbol"]] = o

    rows = ""
    for _, r in df_summary.iterrows():
        sym   = r["symbol"]
        order = order_map.get(sym)

        if order is not None:
            side = str(order.get("side", "")).upper()
            buy_cell  = "✅" if side == "BUY"  else "❌"
            sell_cell = "✅" if side == "SELL" else "❌"
            time_val  = order.get("time", "")
            oid       = order.get("order_id", "")
            resp      = str(order.get("order_response", ""))
            resp_color = "green" if "SUCCESS" in resp.upper() else "red"
            resp_html  = f'<span style="color:{resp_color};font-weight:bold">{resp}</span>'
        else:
            buy_cell  = "❌"
            sell_cell = "❌"
            time_val  = ""
            oid       = ""
            resp_html = ""

        rows += f"""
        <tr>
            <td><b>{sym}</b></td>
            <td>{float(r['lower_band']):.2f}</td>
            <td>{float(r['upper_band']):.2f}</td>
            <td>{float(r['profit']):.2f}</td>
            <td>{float(r['profit_%']):.2f}%</td>
            <td style="font-size:18px">{buy_cell}</td>
            <td style="font-size:18px">{sell_cell}</td>
            <td>{time_val}</td>
            <td>{oid}</td>
            <td>{resp_html}</td>
        </tr>"""

    return f"""
    <table>
        <tr>
            <th>Symbol</th>
            <th>Lower BB</th>
            <th>Upper BB</th>
            <th>Profit (₹)</th>
            <th>Percentage</th>
            <th>Bought</th>
            <th>Sold</th>
            <th>Time</th>
            <th>Order ID</th>
            <th>Response</th>
        </tr>
        {rows}
    </table>"""

# ================================================================
# BUILD FULL EMAIL BODIES
# ================================================================
def build_pre_market_html(df_summary, today):
    table = render_pre_market_table(df_summary)
    total = len(df_summary)
    return f"""
    {TABLE_STYLE}
    <h2>📈 BB Pre-Market Summary — {today}</h2>
    <p>Universe: <b>{total} stocks</b> &nbsp;|&nbsp; BB(20, 2) &nbsp;|&nbsp; Alphabetical order</p>
    {table}
    <p class="footer">Generated by BB LTP Trading Bot</p>
    """

def build_post_market_html(df_summary, df_orders, today):
    table = render_post_market_table(df_summary, df_orders)

    total    = len(df_summary)
    buy_c    = len(df_orders[df_orders["side"] == "BUY"])  if not df_orders.empty else 0
    sell_c   = len(df_orders[df_orders["side"] == "SELL"]) if not df_orders.empty else 0
    failed_c = len(df_orders[df_orders["order_response"].str.upper() != "SUCCESS"]) if not df_orders.empty else 0

    return f"""
    {TABLE_STYLE}
    <h2>📊 BB Post-Market Summary — {today}</h2>
    <p>
        Universe: <b>{total} stocks</b> &nbsp;|&nbsp;
        🟢 BUY: <b>{buy_c}</b> &nbsp;|&nbsp;
        🔴 SELL: <b>{sell_c}</b> &nbsp;|&nbsp;
        ❌ Failed: <b>{failed_c}</b>
    </p>
    {table}
    <p class="footer">Generated by BB LTP Trading Bot</p>
    """

# ================================================================
# SEND EMAIL
# ================================================================
def send_email(subject, html_body):
    app_password = os.getenv("GMAIL_APP_PASSWORD")
    if not app_password:
        print("❌ GMAIL_APP_PASSWORD not found in .env")
        sys.exit(1)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER
    msg["To"]      = RECEIVER
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER, app_password)
        server.sendmail(SENDER, RECEIVER, msg.as_string())

    print(f"✅ Email sent → {RECEIVER}")

# ================================================================
# MAIN
# ================================================================
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:")
        print("  Pre:  python send_email.py pre  summary.csv 'Subject'")
        print("  Post: python send_email.py post summary.csv ltp_orders.csv 'Subject'")
        sys.exit(1)

    mode  = sys.argv[1].lower()
    today = datetime.now().strftime("%Y-%m-%d")

    if mode == "pre":
        summary_csv = sys.argv[2]
        subject     = sys.argv[3]
        df_summary  = pd.read_csv(summary_csv)
        html        = build_pre_market_html(df_summary, today)
        send_email(subject, html)

    elif mode == "post":
        summary_csv = sys.argv[2]
        orders_csv  = sys.argv[3]
        subject     = sys.argv[4]
        df_summary  = pd.read_csv(summary_csv)
        df_orders   = pd.read_csv(orders_csv) if os.path.exists(orders_csv) else pd.DataFrame()
        html        = build_post_market_html(df_summary, df_orders, today)
        send_email(subject, html)

    else:
        print(f"❌ Unknown mode '{mode}'. Use 'pre' or 'post'.")
        sys.exit(1)
