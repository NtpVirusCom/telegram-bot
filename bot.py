from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
import yfinance as yf
import pandas as pd
import logging

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
        data = yf.Ticker(symbol).history(period="3y")

        if data.empty or len(data) < 250:
            await update.message.reply_text("❌ ข้อมูลไม่เพียงพอ")
            return

        close = data["Close"]

        price = close.iloc[-1]
        change_pct = (price - close.iloc[-2]) / close.iloc[-2] * 100

        ema50 = close.ewm(span=50, adjust=False).mean()
        ema100 = close.ewm(span=100, adjust=False).mean()
        ema200 = close.ewm(span=200, adjust=False).mean()

        rsi = calculate_rsi(close).iloc[-1]
        slope200 = ema_slope(ema200)
        macd, signal, hist = calculate_macd(close)

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
            f"• EMA50 : {ema50.iloc[-1]:.2f}\n"
            f"• EMA100: {ema100.iloc[-1]:.2f}\n"
            f"• EMA200: {ema200.iloc[-1]:.2f}\n"
            f"• RSI14 : {rsi:.2f}\n\n"
            f"• MACD   : {macd.iloc[-1]:.3f}\n"
            f"• Signal : {signal.iloc[-1]:.3f}\n"
            f"• Hist   : {hist.iloc[-1]:+.3f}\n\n"
            f"🧠 บทสรุปเชิงกลยุทธ์\n{thesis}"
        )

        await update.message.reply_text(msg)

    except Exception:
        await update.message.reply_text("⚠️ Error")

# =========================
# Main
# =========================
#logging.basicConfig(level=logging.INFO)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

def main():
    logging.info("Telegram Stock Bot (Pro Investor Mode) Started")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, stock_reply))
    app.run_polling()

if __name__ == "__main__":
    main()
