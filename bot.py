import os
import logging
import pandas as pd
import yfinance as yf
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, filters, MessageHandler

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# =========================
# RSI (Wilder Standard)
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
# MACD (12,26,9 Standard)
# =========================
def calculate_macd(close):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()

    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal

    return macd, signal, histogram


# =========================
# EMA Slope (วัดแรง Trend)
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
    supports, resistances = [], []

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
# 1 Month Market Comparison
# =========================
def one_month_return(symbol):
    data = yf.Ticker(symbol).history(period="1mo")
    if data.empty or len(data) < 2:
        return None
    return (data["Close"].iloc[-1] - data["Close"].iloc[0]) / data["Close"].iloc[0] * 100


def market_comparison(stock_ret, nasdaq_ret, sp500_ret):
    result = []

    if stock_ret > nasdaq_ret:
        result.append("🟢 ชนะ NASDAQ")
    else:
        result.append("🔴 แพ้ NASDAQ")

    if stock_ret > sp500_ret:
        result.append("🟢 ชนะ S&P500")
    else:
        result.append("🔴 แพ้ S&P500")

    if stock_ret > max(nasdaq_ret, sp500_ret):
        strength = "🚀 แข็งแกร่งกว่าตลาด (Outperform)"
    elif stock_ret < min(nasdaq_ret, sp500_ret):
        strength = "⚠️ อ่อนแอกว่าตลาด (Underperform)"
    else:
        strength = "⚖️ ใกล้เคียงตลาด"

    return result, strength


# =========================
# Pro Investor Thesis Engine
# =========================
#def pro_investor_thesis(price, ema50, ema100, ema200, rsi, slope200):
def pro_investor_thesis(price, ema50, ema100, ema200, rsi, slope200, macd, signal, hist):
    thesis = []

    # Trend Structure
    if price > ema50 > ema100 > ema200:
        #thesis.append("  📈 โครงสร้างขาขึ้นแข็งแรง (Institutional Uptrend)")
        thesis.append("  📈 แนวโน้มขาขึ้นแข็งแกร่ง (Bullish Trend)")
        trend = "UP"
    elif price < ema200:
        #thesis.append("  📉 ต่ำกว่า EMA200 → โครงสร้างเสีย (Risk Zone)")
        thesis.append("  📉 แนวโน้มขาลง (Bearish Trend)")
        trend = "DOWN"
    else:
        #thesis.append("  ⚖️ Sideway / สะสมพลัง")
        thesis.append("  ⚖️ แนวโน้มแกว่งตัว / สะสมพลัง")
        trend = "SIDE"

    # Momentum
    if rsi > 70:
        #thesis.append("  🔥 RSI สูง → Momentum แรง แต่เริ่มตึง")
        thesis.append("  🔥 โมเมนตัมร้อนแรง แต่เริ่มตึง")
    elif rsi < 30:
        #thesis.append("  ❄️ RSI ต่ำ → Oversold (รอสัญญาณกลับตัว)")
        thesis.append("  ❄️ โมเมนตัมอ่อน รอสัญญาณกลับตัว")
    else:
        thesis.append("  ✅ โมเมนตัมปกติ เหมาะกับการสะสม")

    # MACD Confirmation
    if macd > signal and hist > 0:
        #thesis.append(" 🚀 MACD > Signal → Momentum ขาขึ้นยืนยัน")
        thesis.append(" 🚀 โมเมนตัมขาขึ้นแข็งแกร่ง (Bullish Momentum) และขาขึ้นยืนยัน")
    elif macd < signal and hist < 0:
        #thesis.append(" ⚠️ MACD อ่อนแรง → ระวังแรงขาย")
        thesis.append(" ⚠️ โมเมนตัมอ่อนแรง (Bearish Momentum) ระวังแรงขาย")
    else:
        thesis.append(" ⏳ โมเมนตัมก้ำกึ่ง รอสัญญาณชัด")

    # Trend Strength
    if slope200 > 0:
        #thesis.append("  📐 EMA200 ชี้ขึ้น → Trend ระยะยาวยังแข็ง")
        thesis.append("  📐 EMA200 ชี้ขึ้น → แนวโน้มระยะยาวยังแข็งแกร่ง")
    else:
        #thesis.append("  📐 EMA200 แบน/ลง → ระวัง False Rally")
        thesis.append("  📐 EMA200 แบน/ลง → ระวังสัญญาณหลอก (False Rally)")

    # Final Action
    #if trend == "UP" and 40 <= rsi <= 60:
    if trend == "UP" and 40 <= rsi <= 60 and price <= ema50:
        action = "  🟢 กลยุทธ์: ทยอยสะสม (Buy on Weakness)"
    elif trend == "UP" and rsi > 70:
        action = "  🟡 กลยุทธ์: ถือ / รอย่อ"
    elif trend == "DOWN":
        action = "  🔴 กลยุทธ์: หลีกเลี่ยง / รอฐานใหม่"
    else:
        action = "  🟡 กลยุทธ์: รอดู Confirmation"

    return "\n".join(thesis + [action])

# =========================
# Telegram Handler
# =========================
async def stock_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = update.message.text.upper().strip()

    try:
        data = yf.Ticker(symbol).history(period="5y")

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

        highs = data["High"].values
        lows = data["Low"].values
        zones = calculate_support_resistance(highs, lows)
        supports, resistances = split_support_resistance(zones, price)

        # ===== Market Comparison =====
        stock_1m = one_month_return(symbol)
        nasdaq_1m = one_month_return("^IXIC")
        sp500_1m = one_month_return("^GSPC")

        compare, strength = market_comparison(stock_1m, nasdaq_1m, sp500_1m)

        sr_text = "📐 แนวรับ / แนวต้าน\n"
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
            f"📊 {symbol} | Stock Analysis\n"
            f"💵 ราคา: ${price:.2f} ({change_pct:+.2f}%)\n\n"
            f"• EMA50: {ema50.iloc[-1]:.2f}\n"
            f"• EMA100: {ema100.iloc[-1]:.2f}\n"
            f"• EMA200: {ema200.iloc[-1]:.2f}\n"
            f"• RSI14: {rsi:.2f}\n\n"
            f"• MACD: {macd.iloc[-1]:.3f}\n"
            f"• Signal: {signal.iloc[-1]:.3f}\n"
            f"• Hist: {hist.iloc[-1]:+.3f}\n\n"
            f"{sr_text}\n"
            f"🧪 เปรียบเทียบตลาด 1 เดือน\n"
            f"• {symbol}: {stock_1m:+.2f}%\n"
            f"• NASDAQ: {nasdaq_1m:+.2f}%\n"
            f"• S&P500: {sp500_1m:+.2f}%\n"
            f"{' | '.join(compare)}\n"
            f"{strength}\n\n"
            f"🧠 บทสรุปเชิงกลยุทธ์\n{thesis}"
        )

        await update.message.reply_text(msg)

    #except Exception:
    #    await update.message.reply_text("⚠️ Error")
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("⚠️ เกิดข้อผิดพลาด")


# =========================
# Main
# =========================
#logging.basicConfig(level=logging.INFO)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

def main():
    logging.info("Telegram Stock Bot Started")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, stock_reply))
    app.run_polling()

if __name__ == "__main__":
    main()
