import os
import logging
import pandas as pd
import yfinance as yf
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, filters, MessageHandler
#import openai
from openai import OpenAI


# =========================
# API KEYS
# =========================
#BOT_TOKEN = os.environ.get("BOT_TOKEN")
#OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


#openai.api_key = OPENAI_API_KEY
client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# RSI (Wilder)
# =========================
def calculate_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# =========================
# MACD
# =========================
def calculate_macd(close):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return macd, signal, hist

# =========================
# EMA Slope
# =========================
def ema_slope(series, period=10):
    return series.diff(period).iloc[-1]

# =========================
# Pivot Points
# =========================
def calculate_pivot_points(highs, lows, period=5):
    pivots = []
    for i in range(period, len(highs) - period):
        if highs[i] == max(highs[i-period:i+period+1]):
            pivots.append(highs[i])
        elif lows[i] == min(lows[i-period:i+period+1]):
            pivots.append(lows[i])
    return pivots

# =========================
# Support / Resistance Zones
# =========================
def calculate_support_resistance(highs, lows, period=5, channel_width_pct=0.01):
    pivots = calculate_pivot_points(highs, lows, period)
    zones = []

    for value in pivots:
        width = value * channel_width_pct
        matched = False

        for z in zones:
            if abs(value - z["mid"]) <= width:
                z["mid"] = (z["mid"] + value) / 2
                z["strength"] += 1
                matched = True
                break

        if not matched:
            zones.append({"mid": value, "strength": 1})

    return sorted(zones, key=lambda x: x["strength"], reverse=True)

def split_support_resistance(zones, price, max_levels=2, min_strength=2):
    supports, resistances = [], []

    for z in zones:
        if z["strength"] < min_strength:
            continue
        if z["mid"] < price:
            supports.append(z)
        elif z["mid"] > price:
            resistances.append(z)

    supports = sorted(supports, key=lambda z: abs(price - z["mid"]))[:max_levels]
    resistances = sorted(resistances, key=lambda z: abs(price - z["mid"]))[:max_levels]

    return supports, resistances

# =========================
# Rule-Based Thesis
# =========================
def pro_investor_thesis(price, ema50, ema100, ema200, rsi, slope200, macd, signal, hist):
    thesis = []

    if price > ema50 > ema100 > ema200:
        thesis.append("📈 Institutional Uptrend")
        trend = "UP"
    elif price < ema200:
        thesis.append("📉 Bearish / Risk Zone")
        trend = "DOWN"
    else:
        thesis.append("⚖️ Sideway / Accumulation")
        trend = "SIDE"

    if rsi > 70:
        thesis.append("🔥 Overheated Momentum")
    elif rsi < 30:
        thesis.append("❄️ Oversold")
    else:
        thesis.append("✅ Healthy Momentum")

    if macd > signal and hist > 0:
        thesis.append("🚀 MACD Bullish Confirmation")
    elif macd < signal and hist < 0:
        thesis.append("⚠️ MACD Weak")
    else:
        thesis.append("⏳ MACD Neutral")

    if slope200 > 0:
        thesis.append("📐 Long-term Trend Rising")
    else:
        thesis.append("📐 Long-term Trend Flat/Down")

    if trend == "UP" and rsi < 65:
        action = "🟢 Buy on Weakness"
    elif trend == "UP":
        action = "🟡 Hold / Wait Pullback"
    elif trend == "DOWN":
        action = "🔴 Avoid"
    else:
        action = "🟡 Wait Confirmation"

    return "\n".join(thesis + [action])

# =========================
# AI Thesis Generator (GPT)
# =========================
def ai_thesis_generator(symbol, price, ema50, ema100, ema200,
                        rsi, macd, signal, hist, supports, resistances):

    sr = ""
    if supports:
        sr += f"Supports: {[round(s['mid'],2) for s in supports]}\n"
    if resistances:
        sr += f"Resistances: {[round(r['mid'],2) for r in resistances]}\n"

    prompt = f"""
You are a professional fund manager.

Stock: {symbol}
Price: {price:.2f}

Trend Levels:
EMA50 {ema50:.2f}, EMA100 {ema100:.2f}, EMA200 {ema200:.2f}
Momentum:
RSI {rsi:.2f}
MACD {macd:.3f}, Signal {signal:.3f}, Hist {hist:.3f}

{sr}

Write a concise investment thesis with:
1) Market Structure
2) Risk / Opportunity
3) Action Bias

No indicators names.
Please write everything in Thai.
Max 120 words.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a disciplined institutional investor."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )

    return response.choices[0].message.content


#    response = openai.ChatCompletion.create(
#        model="gpt-4o-mini",
#        messages=[
#            {"role": "system", "content": "You are a disciplined institutional investor."},
#            {"role": "user", "content": prompt}
#        ],
#        temperature=0.3
#    )
#
#    return response.choices[0].message["content"]


# =========================
# Telegram Handler
# =========================
async def stock_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = update.message.text.upper().strip()

    try:
        data = yf.Ticker(symbol).history(period="3y")
        if data.empty or len(data) < 250:
            await update.message.reply_text("❌ ข้อมูลไม่เพียงพอ")
            return

        close = data["Close"]
        highs = data["High"].values
        lows = data["Low"].values

        price = close.iloc[-1]
        change_pct = (price - close.iloc[-2]) / close.iloc[-2] * 100

        ema50 = close.ewm(span=50, adjust=False).mean()
        ema100 = close.ewm(span=100, adjust=False).mean()
        ema200 = close.ewm(span=200, adjust=False).mean()

        rsi = calculate_rsi(close).iloc[-1]
        slope200 = ema_slope(ema200)
        macd, signal, hist = calculate_macd(close)

        zones = calculate_support_resistance(highs, lows)
        supports, resistances = split_support_resistance(zones, price)

        thesis_rule = pro_investor_thesis(
            price, ema50.iloc[-1], ema100.iloc[-1], ema200.iloc[-1],
            rsi, slope200, macd.iloc[-1], signal.iloc[-1], hist.iloc[-1]
        )

        thesis_ai = ai_thesis_generator(
            symbol, price,
            ema50.iloc[-1], ema100.iloc[-1], ema200.iloc[-1],
            rsi, macd.iloc[-1], signal.iloc[-1], hist.iloc[-1],
            supports, resistances
        )

        msg = f"""
📊 {symbol}
💵 ${price:.2f} ({change_pct:+.2f}%)

🧠 Rule-Based View
{thesis_rule}

🤖 AI Investment Thesis
{thesis_ai}
"""

        await update.message.reply_text(msg)

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("⚠️ Error occurred")

# =========================
# Main
# =========================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

def main():
    logging.info("Pro Investor AI Stock Bot Started")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, stock_reply))
    app.run_polling()

if __name__ == "__main__":
    main()
