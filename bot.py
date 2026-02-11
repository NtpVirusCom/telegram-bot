# ========================================================== v.65
# Imports & Config
# ==========================================================
import os
import logging
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import io
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, filters, MessageHandler
from openai import OpenAI


def main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📊 Technical Analysis", callback_data="menu_ta"),
            InlineKeyboardButton("🤖 AI Thesis", callback_data="menu_ai"),            
        ],
        [
            InlineKeyboardButton("📐 SR Zones", callback_data="menu_sr"),
            InlineKeyboardButton("📈 Chart", callback_data="menu_ch"),
        ],
        [
            InlineKeyboardButton("📖 Command Guide", callback_data="menu_help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def post_result_keyboard(symbol: str):
    keyboard = [
        [
            #InlineKeyboardButton("📊 Technical ต่อ", callback_data="menu_ta"),
            InlineKeyboardButton("📊 Technical ต่อ", callback_data=f"again_ta:{symbol}"),
            #InlineKeyboardButton("🤖 AI ต่อ", callback_data="menu_ai"),     
            InlineKeyboardButton("🤖 AI ต่อ", callback_data=f"again_ai:{symbol}"),        
        ],
        [
            #InlineKeyboardButton("📐 SR Zones", callback_data="menu_sr"),
            InlineKeyboardButton("📐 SR ต่อ", callback_data=f"again_sr:{symbol}"),
            #InlineKeyboardButton("📈 Chart", callback_data="menu_ch"),
            InlineKeyboardButton("📈 Chart ต่อ", callback_data=f"again_ch:{symbol}"),
        ],
        [
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_sr_zones_1y(data, price):
    data_1y = data.tail(252)  # ~1Y
    highs = data_1y["High"].values
    lows = data_1y["Low"].values

    support, resistance = calculate_support_resistance_zones(
        highs, lows, price,
        period=4,
        channel_pct=0.01
    )
    return support, resistance



# ==========================================================
# Text Assets
# ==========================================================
START_TEXT = """
🤖 Investment Analysis Bot

ผู้ช่วยวิเคราะห์หุ้นเชิงเทคนิคและกลยุทธ์
ออกแบบในมุมมองนักลงทุนมืออาชีพ

🔍 ฟีเจอร์หลัก
• Technical Analysis (rule-based)
• AI Investment Thesis (institutional tone)
• Support / Resistance อัตโนมัติ
• เปรียบเทียบกับตลาด (NASDAQ / S&P500)

🚀 คำสั่งเริ่มต้น
/ta <symbol>  วิเคราะห์เชิงเทคนิค
/ai <symbol>  AI Investment Thesis
/sr <symbol>  Support / Resistance
/ch <symbol>  แสดงกราฟราคา

📌 ตัวอย่าง
/ta aapl
/ai msft
/sr nvda
/ch pltr

ℹ️ ดูคำสั่งทั้งหมด
/help

⚠️ เพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน
"""

HELP_TEXT = """
📖 Command Guide

━━━━━━━━━━
🟢 CORE
━━━━━━━━━━
/ta <symbol>
• Technical Analysis (rule-based)
• Trend, Momentum, Support / Resistance
• Market comparison + Strategic thesis

/ai <symbol>
• AI Investment Thesis
• มุมมองเชิงกลยุทธ์แบบนักลงทุนสถาบัน
• สรุป Risk / Opportunity / Action bias

━━━━━━━━━━
🟡 DETAIL (coming / optional)
━━━━━━━━━━
/levels <symbol>
• Key Support / Resistance levels

/trend <symbol>
• Market structure & trend direction

/momentum <symbol>
• RSI & momentum regime

━━━━━━━━━━
🔵 AI PRO (future-ready)
━━━━━━━━━━
/bias <symbol>
• Action bias: Accumulate / Hold / Wait / Reduce

/risk <symbol>
• Downside risk & scenario analysis

/outlook <symbol>
• Medium-term outlook (1–3 months)

━━━━━━━━━━
⚙️ UTILITY
━━━━━━━━━━
/start
• เริ่มต้นใช้งาน bot

/help
• ดูรายการคำสั่งทั้งหมด

━━━━━━━━━━
📌 ตัวอย่าง
━━━━━━━━━━
/ta msft
/ai tsla

⚠️ ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน
"""



# ==========================================================
# Environment
# ==========================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

openai_client = OpenAI(api_key=OPENAI_API_KEY)
#client = OpenAI(api_key=OPENAI_API_KEY)


# ==========================================================
# Technical Indicators
# ==========================================================
def calculate_rsi(close, period: int = 14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_macd(close):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()

    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal

    return macd, signal, hist


def ema_slope(series, period: int = 10):
    return series.diff(period).iloc[-1]


# ==========================================================
# Support / Resistance Engine
# ==========================================================
def _pivot_points(highs, lows, window: int = 5):
    pivots = []
    for i in range(window, len(highs) - window):
        if highs[i] == max(highs[i - window:i + window + 1]):
            pivots.append(highs[i])
        elif lows[i] == min(lows[i - window:i + window + 1]):
            pivots.append(lows[i])
    return pivots


#def calculate_support_resistance(highs, lows, window=5, width_pct=0.01):
#def calculate_support_resistance(highs, lows, window=4, width_pct=0.01):
#    pivots = _pivot_points(highs, lows, window)
#    zones = []
#
#    for p in pivots:
#        width = p * width_pct
#        for z in zones:
#            if abs(p - z["mid"]) <= width:
#                z["mid"] = (z["mid"] + p) / 2
#                z["strength"] += 1
#                break
#        else:
#            zones.append({"mid": p, "strength": 1})
#
#    return sorted(zones, key=lambda z: z["strength"], reverse=True)


#def split_support_resistance(zones, price, max_levels=2, min_strength=2):
#    supports, resistances = [], []
#
#    for z in zones:
#        if z["strength"] < min_strength:
#            continue
#        (supports if z["mid"] < price else resistances).append(z)
#
#    supports = sorted(supports, key=lambda z: abs(price - z["mid"]))[:max_levels]
#    resistances = sorted(resistances, key=lambda z: abs(price - z["mid"]))[:max_levels]
#
#    return supports, resistances


#def format_sr_zones(price, support, resistance):
#    lines = ["📐 Support / Resistance (Zones)"]
#
#    if support:
#        for s in support:
#            dist = (price - s["mid"]) / price * 100
#            lines.append(
#                f"• Support: {s['mid']:.2f} (↓ {dist:.2f}%) | S={s['strength']}"
#            )
#    else:
#        lines.append("• Support: ไม่มีระดับที่ชัดเจน")
#
#    if resistance:
#        for r in resistance:
#            dist = (r["mid"] - price) / price * 100
#            lines.append(
#                f"• Resistance: {r['mid']:.2f} (↑ {dist:.2f}%) | S={r['strength']}"
#            )
#    else:
#        lines.append("• Resistance: ไม่มีระดับที่ชัดเจน")
#
#    return "\n".join(lines)



#def format_support_resistance(price, supports, resistances):
#    lines = ["📐 Support / Resistance (Auto)"]
#
#    for i, s in enumerate(supports, 1):
#        dist = (price - s["mid"]) / price * 100
#        lines.append(f"• Support {i}: {s['mid']:.2f} (↓ {dist:.2f}%) | S={s['strength']}")
#
#    for i, r in enumerate(resistances, 1):
#        dist = (r["mid"] - price) / price * 100
#        lines.append(f"• Resistance {i}: {r['mid']:.2f} (↑ {dist:.2f}%) | S={r['strength']}")
#
#    return "\n".join(lines)

def calculate_support_resistance_zones(highs, lows, price, period=4, channel_pct=0.01):
    pivots = _pivot_points(highs, lows, period)
    channel_width = price * channel_pct
    zones = []

    for p in pivots:
        found = False
        for z in zones:
            if abs(p - z["mid"]) <= channel_width:
                z["mid"] = (z["mid"] + p) / 2
                z["strength"] += 1
                found = True
                break
        if not found:
            zones.append({"mid": p, "strength": 1})

    zones = [z for z in zones if z["strength"] >= 2]

    support = sorted(
        [z for z in zones if z["mid"] < price],
        key=lambda x: abs(price - x["mid"])
    )

    resistance = sorted(
        [z for z in zones if z["mid"] > price],
        key=lambda x: abs(price - x["mid"])
    )

    return support[:5], resistance[:5]


def calculate_rr(price, support, resistance):
    if not support or not resistance:
        return None, None, None

    nearest_support = support[0]["mid"]
    nearest_resistance = resistance[0]["mid"]

    risk_pct = (price - nearest_support) / price * 100
    reward_pct = (nearest_resistance - price) / price * 100

    if risk_pct <= 0:
        return None, None, None

    rr = reward_pct / risk_pct if risk_pct > 0 else None
    return risk_pct, reward_pct, rr


# ==========================================================
# Market Comparison
# ==========================================================
def one_month_return(symbol):
    data = yf.Ticker(symbol).history(period="1mo")
    if data.empty or len(data) < 2:
        return None
    return (data["Close"].iloc[-1] - data["Close"].iloc[0]) / data["Close"].iloc[0] * 100


def format_market_comparison(symbol, stock, nasdaq, sp500):
    compare = [
        "🟢 ชนะ NASDAQ" if stock > nasdaq else "🔴 แพ้ NASDAQ",
        "🟢 ชนะ S&P500" if stock > sp500 else "🔴 แพ้ S&P500",
    ]

    if stock > max(nasdaq, sp500):
        strength = "🚀 แข็งแกร่งกว่าตลาด (Outperform)"
    elif stock < min(nasdaq, sp500):
        strength = "⚠️ อ่อนแอกว่าตลาด (Underperform)"
    else:
        strength = "⚖️ ใกล้เคียงตลาด"

    return (
        "🧪 เปรียบเทียบตลาด 1 เดือน\n"
        f"  • {symbol}: {stock:+.2f}%\n"
        f"  • NASDAQ: {nasdaq:+.2f}%\n"
        f"  • S&P500: {sp500:+.2f}%\n"
        f"{' | '.join(compare)}\n"
        f"{strength}"
    )


# ==========================================================
# Strategic Thesis (Rule-based)
# ==========================================================
def pro_investor_thesis(price, ema50, ema100, ema200, rsi, slope200, macd, signal, hist):
    thesis = []

    if price > ema50 > ema100 > ema200:
        thesis.append("  📈 แนวโน้มขาขึ้นแข็งแกร่ง")
        trend = "UP"
    elif price < ema200:
        thesis.append("  📉 แนวโน้มขาลง")
        trend = "DOWN"
    else:
        thesis.append("  ⚖️ แนวโน้มแกว่งตัว / สะสมพลัง")
        trend = "SIDE"

    if rsi > 70:
        thesis.append("  🔥 โมเมนตัมร้อนแรง แต่เริ่มตึง")
    elif rsi < 30:
        thesis.append("  ❄️ โมเมนตัมอ่อน รอสัญญาณกลับตัว")
    else:
        thesis.append("  ✅ โมเมนตัมปกติ เหมาะกับการสะสม")

    if macd > signal and hist > 0:
        thesis.append(" 🚀 โมเมนตัมขาขึ้นแข็งแกร่ง และขาขึ้นยืนยัน")
    elif macd < signal and hist < 0:
        thesis.append(" ⚠️ โมเมนตัมอ่อนแรง ระวังแรงขาย")
    else:
        thesis.append(" ⏳ โมเมนตัมก้ำกึ่ง รอสัญญาณชัด")

    thesis.append(
        "  📐 EMA200 ชี้ขึ้น แนวโน้มระยะยาวยังแข็งแกร่ง"
        if slope200 > 0
        else "  📐 EMA200 แบน/ลง ระวังสัญญาณหลอก (False Rally)"
    )

    if trend == "UP" and 40 <= rsi <= 60 and price <= ema50:
        thesis.append("  🟢 กลยุทธ์: ทยอยสะสม (Buy on Weakness)")
    elif trend == "UP" and rsi > 70:
        thesis.append("  🟡 กลยุทธ์: ถือ / รอย่อ")
    elif trend == "DOWN":
        thesis.append("  🔴 กลยุทธ์: หลีกเลี่ยง / รอฐานใหม่")
    else:
        thesis.append("  🟡 กลยุทธ์: รอดู Confirmation")

    return "\n".join(thesis)


# ==========================================================
# AI Thesis
# ==========================================================
def _format_sr_for_prompt(supports, resistances):
    lines = []
    if supports:
        lines.append("Supports: " + ", ".join(f"{s['mid']:.2f}" for s in supports))
    if resistances:
        lines.append("Resistances: " + ", ".join(f"{r['mid']:.2f}" for r in resistances))
    return "\n".join(lines)


def ai_thesis_generator(symbol, price, ema50, ema100, ema200, rsi,
                        macd, signal, hist, supports, resistances):

    sr_text = _format_sr_for_prompt(supports, resistances)

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

    res = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a disciplined institutional investor."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    return res.choices[0].message.content


# ==========================================================
# Core Analysis Pipeline
# ==========================================================
def analyze(symbol: str) -> dict:
    data = yf.Ticker(symbol).history(period="3y")

    if data.empty or len(data) < 50:
        raise ValueError("SYMBOL_NOT_FOUND")

    # =========================
    # Full data (for trend / EMA / momentum)
    # =========================
    close = data["Close"]

    # =========================
    # 1Y data (for Support / Resistance)
    # =========================
    data_1y = data.tail(252)   # ~252 trading days ≈ 1 year
    highs_1y = data_1y["High"].values
    lows_1y = data_1y["Low"].values

    price = close.iloc[-1]
    change_pct = (price - close.iloc[-2]) / close.iloc[-2] * 100

    ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
    ema100 = close.ewm(span=100, adjust=False).mean().iloc[-1]

    ema200_series = close.ewm(span=200, adjust=False).mean()
    ema200 = ema200_series.iloc[-1]

    rsi = calculate_rsi(close).iloc[-1]
    slope200 = ema_slope(ema200_series)

    macd, signal, hist = calculate_macd(close)

    # ✅ SR ใช้ข้อมูล 1 ปี
    #zones = calculate_support_resistance(highs_1y, lows_1y)
    #supports, resistances = split_support_resistance(zones, price)
    supports, resistances = get_sr_zones_1y(data, price)


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
        "stock_1m": one_month_return(symbol),
        "nasdaq_1m": one_month_return("^IXIC"),
        "sp500_1m": one_month_return("^GSPC"),
    }

# ==========================================================
# Chart Style (Bloomberg / TradingView)
# ==========================================================
def apply_tv_style():
    plt.style.use("dark_background")

    plt.rcParams.update({
        "figure.facecolor": "#0e1117",
        "axes.facecolor": "#0e1117",
        "axes.edgecolor": "#2a2e39",
        "axes.labelcolor": "#cfd3dc",
        "xtick.color": "#cfd3dc",
        "ytick.color": "#cfd3dc",
        "grid.color": "#2a2e39",
        "grid.linestyle": "--",
        "grid.linewidth": 0.5,
        "font.size": 10,
        "legend.frameon": False,
    })

def calculate_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    ha = pd.DataFrame(index=df.index)

    ha["HA_Close"] = (df["Open"] + df["High"] + df["Low"] + df["Close"]) / 4

    ha_open = []
    for i in range(len(df)):
        if i == 0:
            ha_open.append((df["Open"].iloc[0] + df["Close"].iloc[0]) / 2)
        else:
            ha_open.append((ha_open[i-1] + ha["HA_Close"].iloc[i-1]) / 2)

    ha["HA_Open"] = ha_open
    ha["HA_High"] = pd.concat([df["High"], ha["HA_Open"], ha["HA_Close"]], axis=1).max(axis=1)
    ha["HA_Low"]  = pd.concat([df["Low"],  ha["HA_Open"], ha["HA_Close"]], axis=1).min(axis=1)

    return ha


def plot_technical_chart(symbol: str):
    apply_tv_style()
    # โหลดข้อมูล 1 ปี
    data_1y = yf.Ticker(symbol).history(period="1y")

    # โหลดข้อมูล 3 ปี
    data_3y = yf.Ticker(symbol).history(period="3y")

    if data_1y.empty or len(data_1y) < 50:
        raise ValueError("NOT_ENOUGH_DATA")

    close = data_3y["Close"]
    highs = data_3y["High"].values
    lows = data_3y["Low"].values

    # EMA
    #ema50 = close.ewm(span=50).mean()
    #ema100 = close.ewm(span=100).mean()
    #ema200 = close.ewm(span=200).mean()

    ema50 = close.ewm(span=50, adjust=False).mean()
    ema100 = close.ewm(span=100, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()


    # Momentum
    macd, signal, hist = calculate_macd(close)
    rsi = calculate_rsi(close)

    # Support / Resistance (ใช้ข้อมูล 1 ปี)
    price = close.iloc[-1]
    #zones = calculate_support_resistance(highs, lows)
    #supports, resistances = split_support_resistance(zones, price)
    #supports, resistances = calculate_support_resistance_zones(
    #    highs, lows, price
    #)

    # ใช้ข้อมูล 1 ปี เหมือน cmd_sr
    data_sr = data_3y.tail(252)

    supports, resistances = calculate_support_resistance_zones(
        data_sr["High"].values,
        data_sr["Low"].values,
        price
    )



    # ===== Last indicator values =====
    macd_last = macd.iloc[-1]
    signal_last = signal.iloc[-1]
    hist_last = hist.iloc[-1]
    rsi_last = rsi.iloc[-1]


    # แสดงเฉพาะ 1 เดือนล่าสุด
    data_1m = data_3y.tail(21)

    # ===== Heikin Ashi =====
    ha = calculate_heikin_ashi(data_1m)


    close = close.loc[data_1m.index]
    ema50 = ema50.loc[data_1m.index]
    ema100 = ema100.loc[data_1m.index]
    ema200 = ema200.loc[data_1m.index]
    macd = macd.loc[data_1m.index]
    signal = signal.loc[data_1m.index]
    hist = hist.loc[data_1m.index]
    rsi = rsi.loc[data_1m.index]

    # =====================
    # Plot
    # =====================
    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1,
        figsize=(10, 10),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1, 1.5]}
    )

    # Price + EMA
    # ===== Last values =====
    price_last = close.iloc[-1]
    ema50_last = ema50.iloc[-1]
    ema100_last = ema100.iloc[-1]
    ema200_last = ema200.iloc[-1]

    # ===== Plot Price + EMA (with values in legend) =====
    #ax1.plot(close, label=f"Price: {price_last:.2f}")
    #ax1.plot(ema50, label=f"EMA50: {ema50_last:.2f}")
    #ax1.plot(ema100, label=f"EMA100: {ema100_last:.2f}")
    #ax1.plot(ema200, label=f"EMA200: {ema200_last:.2f}")
    # ===== Price + EMA =====
    #ax1.plot(close, label=f"Price {price_last:.2f}",
    #         color="white", linewidth=1.8)
    width = 0.6

    for i in range(len(ha)):
        color = "#00E676" if ha["HA_Close"].iloc[i] >= ha["HA_Open"].iloc[i] else "#FF5252"

        # Wick
        ax1.vlines(
            ha.index[i],
            ha["HA_Low"].iloc[i],
            ha["HA_High"].iloc[i],
            color=color,
            linewidth=1
        )

        # Body
        ax1.bar(
            ha.index[i],
            abs(ha["HA_Close"].iloc[i] - ha["HA_Open"].iloc[i]),
            bottom=min(ha["HA_Open"].iloc[i], ha["HA_Close"].iloc[i]),
            width=width,
            color=color,
            alpha=0.9
        )


    ax1.plot(ema50, label=f"EMA50 {ema50_last:.2f}",
             color="#2962FF", linewidth=1.2)

    ax1.plot(ema100, label=f"EMA100 {ema100_last:.2f}",
             color="#FF6D00", linewidth=1.2)

    ax1.plot(ema200, label=f"EMA200 {ema200_last:.2f}",
             color="#D50000", linewidth=1.6)



    # Support
    #for s in supports:
    #    ax1.axhline(
    #        y=s["mid"],
    #        linestyle="--",
    #        alpha=0.7,
    #        label=f"Support {s['mid']:.2f}"
    #    )

    # Resistance
    #for r in resistances:
    #    ax1.axhline(
    #        y=r["mid"],
    #        linestyle=":",
    #        alpha=0.7,
    #        label=f"Resistance {r['mid']:.2f}"
    #    )

    # ===== Support =====
    for i, s in enumerate(supports, 1):
        ax1.axhline(
            y=s["mid"],
            color="#00E676",
            linestyle="--",
            linewidth=0.9,
            alpha=0.6,
            label=f"S{i}: {s['mid']:.2f}"
        )

    # ===== Resistance =====
    for i, r in enumerate(resistances, 1):
        ax1.axhline(
            y=r["mid"],
            color="#FF5252",
            linestyle=":",
            linewidth=0.9,
            alpha=0.6,
            label=f"R{i}: {r['mid']:.2f}"
        )

    # ===== Legend Title =====
    #ax1.legend(
    #    loc="upper left",
    #    title=f"SR (S={len(supports)} | R={len(resistances)})"
    #)

    legend1 = ax1.legend(
    loc="best",   # ← ให้ matplotlib เลือกตำแหน่งอัตโนมัติ
    framealpha=0.15,
    fontsize=9
    )

    #legend1.set_title(f"SR (S={len(supports)} | R={len(resistances)})")





    #ax1.set_title(f"{symbol} — Price + EMA + MACD + Support / Resistance + RSI")
    #ax1.legend(loc="best")
    #ax1.grid(True)
    #ax1.set_title(
    #    f"{symbol} — Price & Trend Structure",
    #    loc="left",
    #    fontsize=12,
    #    color="white"
    #)
    ax1.set_title(
        f"{symbol} — Heikin Ashi Trend Structure",
        loc="left",
        fontsize=12,
        color="white"
)


    #ax1.legend(loc="upper left")
    ax1.grid(True)


    # MACD
    #ax2.plot(macd, label=f"MACD: {macd_last:.3f}")
    #ax2.plot(signal, label=f"Signal: {signal_last:.3f}")
    #ax2.bar(hist.index, hist, label=f"Hist: {hist_last:+.3f}")
    #ax2.plot(macd, label="MACD")
    #ax2.plot(signal, label="Signal")
    #ax2.bar(hist.index, hist, label="Hist")
    #ax2.legend()
    #ax2.grid(True)
    hist_colors = ["#00E676" if h >= 0 else "#FF5252" for h in hist]

    ax2.bar(
        hist.index,
        hist,
        color=hist_colors,
        alpha=0.8,
        label=f"Hist {hist_last:+.3f}"
    )

    ax2.plot(macd, label=f"MACD {macd_last:.3f}", color="#00B0FF")
    ax2.plot(signal, label=f"Signal {signal_last:.3f}", color="#FFAB00")

    legend1 = ax2.legend(
    loc="best",   # ← ให้ matplotlib เลือกตำแหน่งอัตโนมัติ
    framealpha=0.15,
    fontsize=9
    )

    #legend1.set_title(f"SR (S={len(supports)} | R={len(resistances)})")



    #ax2.legend(loc="upper left")
    ax2.grid(True)


    # RSI
    #ax3.plot(rsi, label="RSI")
    #ax3.plot(rsi, label=f"RSI: {rsi_last:.2f}")
    #ax3.axhline(70, linestyle="--")
    #ax3.axhline(30, linestyle="--")
    #ax3.set_ylim(0, 100)
    #ax3.legend()
    #ax3.grid(True)

    ax3.plot(rsi, label=f"RSI {rsi_last:.2f}",
         color="#AB47BC", linewidth=1.4)

    ax3.axhline(70, color="#FF5252", linestyle="--", alpha=0.5)
    ax3.axhline(30, color="#00E676", linestyle="--", alpha=0.5)

    ax3.set_ylim(0, 100)

    legend1 = ax3.legend(
        loc="best",   # ← ให้ matplotlib เลือกตำแหน่งอัตโนมัติ
        framealpha=0.15,
        fontsize=9
    )

    #legend1.set_title(f"SR (S={len(supports)} | R={len(resistances)})")



    #ax3.legend(loc="upper left")
    ax3.grid(True)


    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)

    return buf




# ==========================================================
# Telegram Handlers
# ==========================================================
#async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#    await update.message.reply_text(START_TEXT)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        START_TEXT,
        reply_markup=main_menu_keyboard()
    )


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "menu_ta":
        context.user_data["mode"] = "ta"
        await query.message.reply_text("🔎 พิมพ์สัญลักษณ์หุ้น เช่น `AAPL`")

    elif data == "menu_ai":
        context.user_data["mode"] = "ai"
        await query.message.reply_text("🤖 พิมพ์สัญลักษณ์หุ้น เช่น `MSFT`")

    elif data == "menu_sr":
        context.user_data["mode"] = "sr"
        await query.message.reply_text("📐 พิมพ์สัญลักษณ์หุ้น เช่น `TSLA`")

    elif data == "menu_ch":
        context.user_data["mode"] = "ch"
        await query.message.reply_text("📈 พิมพ์สัญลักษณ์หุ้น เช่น `NVDA`")

    elif data == "menu_help":
        await query.message.reply_text(HELP_TEXT)

    elif data == "menu_home":
        await query.message.reply_text(
            START_TEXT,
            reply_markup=main_menu_keyboard()
        )

    
    # 🔁 วิเคราะห์ต่อทันที
    elif data.startswith("again_ta:"):
        symbol = data.split(":")[1]
        context.args = [symbol]
        await cmd_ta(query, context)

    elif data.startswith("again_ai:"):
        symbol = data.split(":")[1]
        context.args = [symbol]
        await cmd_ai(query, context)

    elif data.startswith("again_sr:"):
        symbol = data.split(":")[1]
        context.args = [symbol]
        await cmd_sr(query, context)

    elif data.startswith("again_ch:"):
        symbol = data.split(":")[1]
        context.args = [symbol]
        await cmd_ch(query, context)



async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    if not mode:
        return

    symbol = update.message.text.strip().upper()
    context.args = [symbol]

    if mode == "ta":
        await cmd_ta(update, context)
    elif mode == "ai":
        await cmd_ai(update, context)
    elif mode == "sr":
        await cmd_sr(update, context)
    elif mode == "ch":
        await cmd_ch(update, context)





async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)
    context.user_data["last_symbol"] = symbol



async def cmd_ta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0].upper()
    context.user_data["last_symbol"] = symbol

    
    try:
        d = analyze(symbol)
    except ValueError:
        await update.message.reply_text(
            "❌ ไม่พบชื่อหุ้นนี้\nกรุณาตรวจสอบสัญลักษณ์อีกครั้ง"
        )
        return

    thesis = pro_investor_thesis(
        d['price'],
        d['ema50'],
        d['ema100'],
        d['ema200'],
        d['rsi'],
        d['slope200'],
        d['macd'].iloc[-1],
        d['signal'].iloc[-1],
        d['hist'].iloc[-1],
    )

    text = (
        f"📊 {symbol}\n"
        f"💵 ราคา: ${d['price']:.2f} ({d['change_pct']:+.2f}%)\n\n"
        f"• EMA50: {d['ema50']:.2f}\n"
        f"• EMA100: {d['ema100']:.2f}\n"
        f"• EMA200: {d['ema200']:.2f}\n"
        f"• RSI14: {d['rsi']:.2f}\n\n"
        f"• MACD: {d['macd'].iloc[-1]:.3f}\n"
        f"• Signal: {d['signal'].iloc[-1]:.3f}\n"
        f"• Hist: {d['hist'].iloc[-1]:+.3f}\n\n"
        #f"{format_support_resistance(d['price'], d['supports'], d['resistances'])}\n\n"
        #f"{format_sr_zones(d['price'], d['supports'], d['resistances'])}\n\n"
        f"{format_market_comparison(symbol, d['stock_1m'], d['nasdaq_1m'], d['sp500_1m'])}\n\n"
        f"🧠 บทสรุปเชิงกลยุทธ์\n"
        f"{thesis}"
    )




    await update.message.reply_text(
        text,
        reply_markup=post_result_keyboard(symbol)
    )
    #await update.message.reply_text(
    #    text,
    #    reply_markup=post_result_keyboard()
    #)


    
async def cmd_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0].upper()

    try:
        d = analyze(symbol)
    except ValueError:
        await update.message.reply_text(
            "❌ ไม่พบชื่อหุ้นนี้\nกรุณาตรวจสอบสัญลักษณ์อีกครั้ง"
        )
        return


    ai = ai_thesis_generator(
        symbol,
        d["price"],
        d["ema50"],
        d["ema100"],
        d["ema200"],
        d["rsi"],
        d["macd"].iloc[-1],
        d["signal"].iloc[-1],
        d["hist"].iloc[-1],
        d["supports"],
        d["resistances"],
    )

    text = (
        "📊 {symbol}\n"
        "💵 ราคา: ${price:.2f} ({change:+.2f}%)\n\n"
        "🤖 AI Thesis\n{ai}"
    ).format(
        symbol=symbol,
        price=d["price"],
        change=d["change_pct"],
        ai=ai,
    )

    await update.message.reply_text(
        text,
        reply_markup=post_result_keyboard(symbol)
    )
    #await update.message.reply_text(
    #    text,
    #    reply_markup=post_result_keyboard()
    #)


async def cmd_sr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0].upper()

    try:
        data_1y = yf.Ticker(symbol).history(period="1y")
        if data_1y.empty or len(data_1y) < 50:
            raise ValueError
    except Exception:
        await update.message.reply_text("❌ ไม่พบชื่อหุ้นนี้")
        return

    price = data_1y["Close"].iloc[-1]
    highs = data_1y["High"].values
    lows = data_1y["Low"].values
    prev_price = data_1y["Close"].iloc[-2]
    change = (price - prev_price) / prev_price * 100


    support, resistance = calculate_support_resistance_zones(
        highs, lows, price
    )

    risk_pct, reward_pct, rr = calculate_rr(price, support, resistance)

    text = f"📐 SR Zones — {symbol}\n"
    #text += f"💵 Price: {price:.2f}\n\n"
    text += f"💵 ราคา: ${price:.2f} ({change:+.2f}%)\n\n"
    #text += f"💵 ราคา: ${d['price']:.2f} ({d['change_pct']:+.2f}%)\n\n"

    text += "🟢 Support Zones\n"
    if support:
        for s in support:
            dist = (price - s["mid"]) / price * 100
            text += f"  • {s['mid']:.2f} (↓ {dist:.2f}%) | S={s['strength']}\n"
    else:
        text += "  • ไม่มีระดับที่ชัดเจน\n"

    text += "\n🔴 Resistance Zones\n"
    if resistance:
        for r in resistance:
            dist = (r["mid"] - price) / price * 100
            text += f"  • {r['mid']:.2f} (↑ {dist:.2f}%) | S={r['strength']}\n"
    else:
        text += "  • ไม่มีระดับที่ชัดเจน\n"

    if rr:
        text += (
            f"\n⚖️ Risk / Reward\n"
            f"  • Downside risk: ↓{risk_pct:.2f}%\n"
            f"  • Upside reward: ↑{reward_pct:.2f}%\n"
            f"  • R/R Ratio: {rr:.2f}x\n"
        )

        if rr >= 3:
            text += "🟢 โครงสร้างราคาน่าสนใจ (Asymmetric)\n"
        elif rr >= 2:
            text += "🟡 โครงสร้างสมดุล\n"
        else:
            text += "🔴 Risk สูงเมื่อเทียบกับ Reward\n"
    else:
        text += "• ไม่สามารถประเมิน Risk / Reward ได้\n"

    #await update.message.reply_text(
    #    text,
    #    reply_markup=post_result_keyboard()
    #)
    await update.message.reply_text(
        text,
        reply_markup=post_result_keyboard(symbol)
    )



async def cmd_ch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0].upper()

    try:
        chart = plot_technical_chart(symbol)
    except Exception:
        await update.message.reply_text("❌ ไม่สามารถสร้างกราฟได้")
        return

    await update.message.reply_photo(
        photo=chart,
        caption=f"📈 {symbol}\nPrice + EMA + MACD + Support / Resistance + RSI",
        #reply_markup=post_result_keyboard()
        reply_markup=post_result_keyboard(symbol)
    )


# ==========================================================
# App Bootstrap
# ==========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

def main():
    logging.info("Pro Investor AI Stock Bot Started")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))

    app.add_handler(CommandHandler("ta", cmd_ta))
    app.add_handler(CommandHandler("ai", cmd_ai))
    app.add_handler(CommandHandler("sr", cmd_sr))
    app.add_handler(CommandHandler("ch", cmd_ch))

    app.run_polling()


if __name__ == "__main__":
    main()
