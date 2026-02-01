import os
import logging
import yfinance as yf
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from openai import OpenAI

# =========================
# ENV
# =========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# RSI
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
# EMA slope
# =========================
def ema_slope(series, period=10):
    return series.diff(period).iloc[-1]

# =========================
# Support / Resistance
# =========================
def calculate_pivot_points(highs, lows, period=5):
    pivots = []
    for i in range(period, len(highs) - period):
        if highs[i] == max(highs[i-period:i+period+1]):
            pivots.append(highs[i])
        elif lows[i] == min(lows[i-period:i+period+1]):
            pivots.append(lows[i])
    return pivots

def calculate_support_resistance(highs, lows, period=5, channel_width_pct=0.01):
    pivots = calculate_pivot_points(highs, lows, period)
    zones = []
    for value in pivots:
        width = value * channel_width_pct
        for z in zones:
            if abs(value - z["mid"]) <= width:
                z["mid"] = (z["mid"] + value) / 2
                z["strength"] += 1
                break
        else:
            zones.append({"mid": value, "strength": 1})
    return sorted(zones, key=lambda x: x["strength"], reverse=True)

def split_support_resistance(zones, price, max_levels=2, min_strength=2):
    supports, resistances = [], []
    for z in zones:
        if z["strength"] < min_strength:
            continue
        (supports if z["mid"] < price else resistances).append(z)

    supports = sorted(supports, key=lambda z: abs(price - z["mid"]))[:max_levels]
    resistances = sorted(resistances, key=lambda z: abs(price - z["mid"]))[:max_levels]
    return supports, resistances

def format_support_resistance(price, supports, resistances):
    lines = ["📐 Support / Resistance (Auto)"]
    for i, s in enumerate(supports, 1):
        dist = (price - s["mid"]) / price * 100
        lines.append(
            f"• Support {i}: {s['mid']:.2f} (↓ {dist:.2f}%) | S={s['strength']}"
        )
    for i, r in enumerate(resistances, 1):
        dist = (r["mid"] - price) / price * 100
        lines.append(
            f"• Resistance {i}: {r['mid']:.2f} (↑ {dist:.2f}%) | S={r['strength']}"
        )
    return "\n".join(lines)

# =========================
# Market Comparison
# =========================
def one_month_return(symbol):
    data = yf.Ticker(symbol).history(period="1mo")
    if data.empty or len(data) < 2:
        return None
    return (data["Close"].iloc[-1] - data["Close"].iloc[0]) / data["Close"].iloc[0] * 100

def format_market_comparison(symbol, stock, nasdaq, sp500):
    compare = []
    compare.append("🟢 ชนะ NASDAQ" if stock > nasdaq else "🔴 แพ้ NASDAQ")
    compare.append("🟢 ชนะ S&P500" if stock > sp500 else "🔴 แพ้ S&P500")

    if stock > max(nasdaq, sp500):
        strength = "🚀 แข็งแกร่งกว่าตลาด (Outperform)"
    elif stock < min(nasdaq, sp500):
        strength = "⚠️ อ่อนแอกว่าตลาด (Underperform)"
    else:
        strength = "⚖️ ใกล้เคียงตลาด"

    return (
        "🧪 เปรียบเทียบตลาด 1 เดือน\n"
        f"• {symbol}: {stock:+.2f}%\n"
        f"• NASDAQ: {nasdaq:+.2f}%\n"
        f"• S&P500: {sp500:+.2f}%\n"
        f"{' | '.join(compare)}\n"
        f"{strength}"
    )

# =========================
# STRATEGIC THESIS
# =========================
#def pro_investor_thesis(price, ema50, ema100, ema200, rsi, macd, signal, hist):
def pro_investor_thesis(price, ema50, ema100, ema200, rsi, slope200, macd, signal, hist):
    thesis = []

    if price > ema50 > ema100 > ema200:
        #thesis.append("📈 โครงสร้างแนวโน้มเป็นขาขึ้นแข็งแกร่ง")
        thesis.append("  📈 แนวโน้มขาขึ้นแข็งแกร่ง")
        trend = "UP"
    elif price < ema200:
        #thesis.append("📉 แนวโน้มหลักเป็นขาลง ระวังแรงขาย")
        thesis.append("  📉 แนวโน้มขาลง")
        trend = "DOWN"
    else:
        #thesis.append("⚖️ ราคาอยู่ในช่วงสะสม / แกว่งตัว")
        thesis.append("  ⚖️ แนวโน้มแกว่งตัว / สะสมพลัง")
        trend = "SIDE"

    if rsi > 70:
        #thesis.append("🔥 โมเมนตัมร้อนแรง มีความเสี่ยงย่อ")
        thesis.append("  🔥 โมเมนตัมร้อนแรง แต่เริ่มตึง")
    elif rsi < 30:
        #thesis.append("❄️ โมเมนตัมอ่อน เริ่มน่าสนใจเชิงกลับตัว")
        thesis.append("  ❄️ โมเมนตัมอ่อน รอสัญญาณกลับตัว")
    else:
        #thesis.append("✅ โมเมนตัมปกติ")
        thesis.append("  ✅ โมเมนตัมปกติ เหมาะกับการสะสม")

    if macd > signal and hist > 0:
        #thesis.append("🚀 โมเมนตัมขาขึ้นได้รับการยืนยัน")
        thesis.append(" 🚀 โมเมนตัมขาขึ้นแข็งแกร่ง และขาขึ้นยืนยัน")
    elif macd < signal and hist < 0:
        #thesis.append("⚠️ โมเมนตัมขาลงยังครองตลาด")
        thesis.append(" ⚠️ โมเมนตัมอ่อนแรง ระวังแรงขาย")
    else:
        thesis.append(" ⏳ โมเมนตัมก้ำกึ่ง รอสัญญาณชัด")

    # Trend Strength
    if slope200 > 0:
        #thesis.append("  📐 EMA200 ชี้ขึ้น → Trend ระยะยาวยังแข็ง")
        thesis.append("  📐 EMA200 ชี้ขึ้น แนวโน้มระยะยาวยังแข็งแกร่ง")
    else:
        #thesis.append("  📐 EMA200 แบน/ลง → ระวัง False Rally")
        thesis.append("  📐 EMA200 แบน/ลง ระวังสัญญาณหลอก (False Rally)")

    #if price > ema50 and rsi < 60:
    if trend == "UP" and 40 <= rsi <= 60 and price <= ema50:
        #thesis.append("🟢 กลยุทธ์: ทยอยสะสมเมื่อย่อ")
        thesis.append("  🟢 กลยุทธ์: ทยอยสะสม (Buy on Weakness)")
    #elif rsi > 70:
    elif trend == "UP" and rsi > 70:
        thesis.append("  🟡 กลยุทธ์: ถือ / รอย่อ")
    elif trend == "DOWN":
        thesis.append("  🔴 กลยุทธ์: หลีกเลี่ยง / รอฐานใหม่")
    else:
        #thesis.append("🔴 กลยุทธ์: รอดู Confirmation")
        thesis.append("  🟡 กลยุทธ์: รอดู Confirmation")

    return "\n".join(thesis)

# =========================
# AI THESIS
# =========================
def format_sr_for_prompt(supports, resistances):
    lines = []
    if supports:
        lines.append(
            "Supports: " + ", ".join(f"{s['mid']:.2f}" for s in supports)
        )
    if resistances:
        lines.append(
            "Resistances: " + ", ".join(f"{r['mid']:.2f}" for r in resistances)
        )
    return "\n".join(lines)


def ai_thesis_generator(symbol, price, ema50, ema100, ema200,
                        rsi, macd, signal, hist, supports, resistances):

    sr_text = format_sr_for_prompt(supports, resistances)

    prompt = f"""
You are a professional fund manager.

Stock: {symbol}
Price: {price:.2f}

Market structure:
EMA levels: {ema50:.2f}, {ema100:.2f}, {ema200:.2f}

Momentum context:
RSI {rsi:.2f}
MACD {macd:.2f}, Signal {signal:.2f}, Hist {hist:.2f}

Key price zones:
{sr_text}

Write a concise Thai investment thesis in bullet points using this structure:
1) Market structure (trend & price behavior)
2) Risk & opportunity around key price zones
3) Action bias (accumulate / wait / avoid)

Do not mention indicator names explicitly.
Write in Thai.
Max 120 words.
"""

    prompt0 = f"""
You are a professional institutional investor.

Asset: {symbol}
Current price: {price:.2f}

Reference price levels:
• Short-term: {ema50:.2f}
• Medium-term: {ema100:.2f}
• Long-term: {ema200:.2f}

Momentum context:
• Relative strength level: {rsi:.1f}
• Momentum balance: {macd - signal:+.3f}

Key price zones:
{sr_text}

Instructions:
Write a concise Thai investment thesis in bullet points using this structure:

1) Price positioning
- Describe where the current price stands relative to key reference levels

2) Downside risk
- Identify key downside risk levels and what they imply

3) Upside opportunity
- Describe upside potential and nearby resistance areas

4) Action bias
- Recommend one clear stance: Accumulate / Hold / Wait / Reduce

Rules:
• Do not mention indicator names
• Use price levels and numbers
• Be professional and neutral
• Write in Thai.
• Max 120 words
"""

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a disciplined institutional investor."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )
    return res.choices[0].message.content

# =========================
# CORE ANALYSIS
# =========================
def analyze(symbol):
    data = yf.Ticker(symbol).history(period="3y")
    close = data["Close"]
    highs, lows = data["High"].values, data["Low"].values

    price = close.iloc[-1]
    change_pct = (price - close.iloc[-2]) / close.iloc[-2] * 100

    ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
    ema100 = close.ewm(span=100, adjust=False).mean().iloc[-1]
    #ema200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
    ema200_series = close.ewm(span=200, adjust=False).mean()
    ema200 = ema200_series.iloc[-1]

    rsi = calculate_rsi(close).iloc[-1]
    slope200 = ema_slope(ema200_series)
    #slope200 = ema_slope(ema200)
    macd, signal, hist = calculate_macd(close)

    zones = calculate_support_resistance(highs, lows)
    supports, resistances = split_support_resistance(zones, price)

    stock_1m = one_month_return(symbol)
    nasdaq_1m = one_month_return("^IXIC")
    sp500_1m = one_month_return("^GSPC")

    return {
        "price": price,
        "change_pct": change_pct,
        "ema50": ema50,
        "ema100": ema100,
        "ema200": ema200,
        "slope200": slope200,
        "rsi": rsi,
        "macd": macd,
        "signal": signal,
        "hist": hist,
        "supports": supports,
        "resistances": resistances,
        "stock_1m": stock_1m,
        "nasdaq_1m": nasdaq_1m,
        "sp500_1m": sp500_1m
    }

# =========================
# HANDLER
# =========================
async def cmd_a(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0].upper()
    d = analyze(symbol)

    sr_text = format_support_resistance(
        d["price"], d["supports"], d["resistances"]
    )

    market_text = format_market_comparison(
        symbol, d["stock_1m"], d["nasdaq_1m"], d["sp500_1m"]
    )

    thesis = pro_investor_thesis(
        d["price"], d["ema50"], d["ema100"], d["ema200"],
        d["rsi"],d["slope200"],
        d["macd"].iloc[-1], d["signal"].iloc[-1], d["hist"].iloc[-1]
    )

    await update.message.reply_text(
        f"📊 {symbol}\n"
        f"💵 ราคา: ${d['price']:.2f} ({d['change_pct']:+.2f}%)\n\n"
        f"• EMA50: {d['ema50']:.2f}\n"
        f"• EMA100: {d['ema100']:.2f}\n"
        f"• EMA200: {d['ema200']:.2f}\n"
        f"• RSI14: {d['rsi']:.2f}\n\n"
        f"• MACD: {d['macd'].iloc[-1]:.3f}\n"
        f"• Signal: {d['signal'].iloc[-1]:.3f}\n"
        f"• Hist: {d['hist'].iloc[-1]:+.3f}\n\n"
        f"{sr_text}\n\n"
        f"{market_text}\n\n"
        f"🧠 บทสรุปเชิงกลยุทธ์\n{thesis}"
    )

async def cmd_b(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0].upper()
    d = analyze(symbol)

    ai = ai_thesis_generator(
        symbol, d["price"],
        d["ema50"], d["ema100"], d["ema200"],
        d["rsi"],  d["macd"].iloc[-1],
        d["signal"].iloc[-1], d["hist"].iloc[-1],
        d["supports"], d["resistances"]
    )

    await update.message.reply_text(
        #f"📊 {symbol}\n💵 {d['price']:.2f}\n\n🤖 AI Thesis\n{ai}"
        f"📊 {symbol}\n"
        f"💵 ราคา: ${d['price']:.2f} ({d['change_pct']:+.2f}%)\n\n"
        f"🤖 AI Thesis\n{ai}"
    )

# =========================
# MAIN
# =========================
def main():
    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("a", cmd_a))
    app.add_handler(CommandHandler("b", cmd_b))
    app.run_polling()

if __name__ == "__main__":
    main()
