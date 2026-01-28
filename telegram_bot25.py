import os
import logging
import pandas as pd
import yfinance as yf
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, filters, MessageHandler

BOT_TOKEN = os.environ.get("BOT_TOKEN")

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
# Pivot High / Low
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
            zones.append({
                "mid": value,
                "strength": 1
            })

    return sorted(zones, key=lambda x: x["strength"], reverse=True)


# =========================
# Auto Split Support / Resistance
# =========================
def split_support_resistance(zones, price, max_levels=2, min_strength=2):
    supports = []
    resistances = []

    for z in zones:
        if z["strength"] < min_strength:
            continue

        if z["mid"] < price:
            supports.append(z)
        elif z["mid"] > price:
            resistances.append(z)

    supports = sorted(
        supports,
        key=lambda z: (abs(price - z["mid"]), -z["strength"])
    )[:max_levels]

    resistances = sorted(
        resistances,
        key=lambda z: (abs(price - z["mid"]), -z["strength"])
    )[:max_levels]

    return supports, resistances


# =========================
# Pro Investor Thesis
# =========================
def pro_investor_thesis(price, ema50, ema100, ema200, rsi, slope200, macd, signal, hist):
    thesis = []

    if price > ema50 > ema100 > ema200:
        thesis.append("📈 Bullish Trend (Institutional Uptrend)")
        trend = "UP"
    elif price < ema200:
        thesis.append("📉 Bearish Trend (Risk Zone)")
        trend = "DOWN"
    else:
        thesis.append("⚖️ Sideway / Accumulation")
        trend = "SIDE"

    if rsi > 70:
        thesis.append("🔥 Momentum ร้อนแรง (Overbought)")
    elif rsi < 30:
        thesis.append("❄️ Momentum อ่อน (Oversold)")
    else:
        thesis.append("✅ Momentum ปกติ")

    if macd > signal and hist > 0:
        thesis.append("🚀 MACD ยืนยันขาขึ้น")
    elif macd < signal and hist < 0:
        thesis.append("⚠️ MACD อ่อนแรง")
    else:
        thesis.append("⏳ MACD ก้ำกึ่ง")

    if slope200 > 0:
        thesis.append("📐 EMA200 ชี้ขึ้น (Long-term แข็งแรง)")
    else:
        thesis.append("📐 EMA200 แบน/ลง (ระวัง False Rally)")

    if trend == "UP" and 40 <= rsi <= 60:
        action = "🟢 Strategy: Buy on Weakness"
    elif trend == "UP" and rsi > 70:
        action = "🟡 Strategy: Hold / Wait Pullback"
    elif trend == "DOWN":
        action = "🔴 Strategy: Avoid"
    else:
        action = "🟡 Strategy: Wait Confirmation"

    return "\n".join(thesis + [action])


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

        zones = calculate_support_resistance(
            highs, lows,
            period=5,
            channel_width_pct=0.01
        )

        supports, resistances = split_support_resistance(
            zones, price,
            max_levels=2,
            min_strength=2
        )

        sr_text = "📐 Support / Resistance (Auto)\n"
        for i, s in enumerate(supports, 1):
            dist = (price - s["mid"]) / price * 100
            sr_text += f"• Support {i}: {s['mid']:.2f} (↓ {dist:.2f}%) | S={s['strength']}\n"

        for i, r in enumerate(resistances, 1):
            dist = (r["mid"] - price) / price * 100
            sr_text += f"• Resistance {i}: {r['mid']:.2f} (↑ {dist:.2f}%) | S={r['strength']}\n"

        thesis = pro_investor_thesis(
            price,
            ema50.iloc[-1],
            ema100.iloc[-1],
            ema200.iloc[-1],
            rsi,
            slope200,
            macd.iloc[-1],
            signal.iloc[-1],
            hist.iloc[-1]
        )

        msg = (
            f"📊 {symbol} | Pro Investor Analysis\n"
            f"💵 ราคา: ${price:.2f} ({change_pct:+.2f}%)\n\n"
            f"• EMA50 : {ema50.iloc[-1]:.2f}\n"
            f"• EMA100: {ema100.iloc[-1]:.2f}\n"
            f"• EMA200: {ema200.iloc[-1]:.2f}\n"
            f"• RSI14 : {rsi:.2f}\n\n"
            f"• MACD  : {macd.iloc[-1]:.3f}\n"
            f"• Signal: {signal.iloc[-1]:.3f}\n"
            f"• Hist  : {hist.iloc[-1]:+.3f}\n\n"
            f"{sr_text}\n"
            f"🧠 Strategic View\n{thesis}"
        )

        await update.message.reply_text(msg)

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("⚠️ Error occurred")


# =========================
# Main
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

def main():
    logging.info("🤖 Telegram Stock Bot (Pro Investor Mode) Started")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, stock_reply))
    app.run_polling()

if __name__ == "__main__":
    main()
