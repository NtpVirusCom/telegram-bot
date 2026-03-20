# ==========================================================
# Imports & Config
# ==========================================================
import io
import logging
import matplotlib.pyplot as plt
import math
import os
import pandas as pd
import requests
import yfinance as yf
from io import StringIO

from openai import OpenAI
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, filters, MessageHandler


# ==========================================================
# MODIFY MENU
# ==========================================================
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
            InlineKeyboardButton("🆕 Mansfield RS", callback_data="menu_man"),
            InlineKeyboardButton("🚀 Stage Analysis", callback_data="menu_stage"),
        ],
        [
            InlineKeyboardButton("📖 Command Guide", callback_data="menu_help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def post_result_keyboard(symbol: str):
    keyboard = [
        [
            InlineKeyboardButton("📊 Technical ต่อ", callback_data=f"again_ta:{symbol}"),
            InlineKeyboardButton("🤖 AI ต่อ", callback_data=f"again_ai:{symbol}"),        
        ],
        [
            InlineKeyboardButton("📐 SR Zones ต่อ", callback_data=f"again_sr:{symbol}"),
            InlineKeyboardButton("📈 Chart ต่อ", callback_data=f"again_ch:{symbol}"),
        ],
        [
            InlineKeyboardButton("🆕 Mans RS ต่อ", callback_data=f"again_man:{symbol}"),
            InlineKeyboardButton("🚀 Stage ต่อ", callback_data=f"again_stage:{symbol}"),
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

🚀 คำสั่งเริ่มต้น

📌 ตัวอย่าง

ℹ️ ดูคำสั่งทั้งหมด

⚠️ เพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน
"""

HELP_TEXT = """
📖 Command Guide

━━━━━━━━━━
🟢 CORE
━━━━━━━━━━

━━━━━━━━━━
🟡 DETAIL (coming / optional)
━━━━━━━━━━

━━━━━━━━━━
🔵 AI PRO (future-ready)
━━━━━━━━━━

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

# ==========================================================
# Mansfield RS (StageAnalysis - Weekly, Unflattened)
# ==========================================================
def calculate_mansfield_rs(symbol: str, benchmark: str = "^GSPC", ma_length: int = 52):
    # ดึงข้อมูลแบบ Weekly
    stock = yf.Ticker(symbol).history(period="3y", interval="1wk")
    index = yf.Ticker(benchmark).history(period="3y", interval="1wk")

    if stock.empty or index.empty:
        raise ValueError("NOT_ENOUGH_DATA")

    df = pd.DataFrame({
        "stock": stock["Close"],
        "index": index["Close"]
    }).dropna()

    # RS Line (เหมือน Pine)
    df["rs"] = df["stock"] / df["index"] * 100

    # MA 52 สัปดาห์
    df["rs_ma"] = df["rs"].rolling(ma_length).mean()

    return df.tail(104)  # ~2 ปีล่าสุด

# ==========================================================
# SATA CALCULATION (Stage Analysis Technical Attributes)
# ==========================================================
def calculate_sata(symbol: str):

    stock = yf.Ticker(symbol).history(period="3y", interval="1wk")
    benchmark = yf.Ticker("^GSPC").history(period="3y", interval="1wk")

    df = pd.DataFrame({
        "Close": stock["Close"],
        "High": stock["High"],
        "Low": stock["Low"],
        "Volume": stock["Volume"],
        "Index": benchmark["Close"]
    }).dropna()

    # ===============================
    # Moving Averages
    # ===============================
    df["ma10"] = df["Close"].rolling(10).mean()
    df["ma30"] = df["Close"].rolling(30).mean()
    df["ma40"] = df["Close"].rolling(40).mean()

    df["ma10_slope"] = df["ma10"].diff()
    df["ma30_slope"] = df["ma30"].diff()
    df["ma40_slope"] = df["ma40"].diff()

    # ===============================
    # Mansfield RS
    # ===============================
    rs = df["Close"] / df["Index"]
    rs_ma = rs.rolling(52).mean()
    mansfield = ((rs / rs_ma) - 1) * 100
    rs_slope = mansfield.diff()

    # ===============================
    # Volume MA
    # ===============================
    df["vol_ma"] = df["Volume"].rolling(10).mean()

    # ===============================
    # SATA-10 Attributes
    # ===============================
    sata = pd.DataFrame(index=df.index)

    # 1 Price > 30W
    sata["a1"] = (df["Close"] > df["ma30"]).astype(int)

    # 2 30W MA Rising
    sata["a2"] = (df["ma30_slope"] > 0).astype(int)

    # 3 Price > 40W
    sata["a3"] = (df["Close"] > df["ma40"]).astype(int)

    # 4 40W MA Rising
    sata["a4"] = (df["ma40_slope"] > 0).astype(int)

    # 5 10W > 30W
    sata["a5"] = (df["ma10"] > df["ma30"]).astype(int)

    # 6 10W Rising
    sata["a6"] = (df["ma10_slope"] > 0).astype(int)

    # 7 Mansfield > 0
    sata["a7"] = (mansfield > 0).astype(int)

    # 8 RS Rising
    sata["a8"] = (rs_slope > 0).astype(int)

    # 9 Higher High
    sata["a9"] = (df["High"] > df["High"].shift(1)).astype(int)

    # 10 Volume Confirmation
    sata["a10"] = (df["Volume"] > df["vol_ma"]).astype(int)

    # ===============================
    # Final Score
    # ===============================
    sata["score"] = sata.sum(axis=1)

    #return df, sata
    return df, sata, rs

def detect_stage_pro(df, sata):

    df = df.copy()

    # ===== 40W MA Slope =====
    df["ma40"] = df["Close"].rolling(40).mean()
    df["ma40_slope"] = df["ma40"].diff()

    latest = df.iloc[-1]

    stage = "Unknown"

    # =========================
    # Stage 2
    # =========================
    if latest["Close"] > latest["ma40"] and latest["ma40_slope"] > 0:
        stage = "Stage 2"

    # =========================
    # Stage 4
    # =========================
    elif latest["Close"] < latest["ma40"] and latest["ma40_slope"] < 0:
        stage = "Stage 4"

    # =========================
    # Stage 1
    # =========================
    elif abs(latest["ma40_slope"]) < 0.01:
        stage = "Stage 1"

    # =========================
    # Stage 3
    # =========================
    else:
        stage = "Stage 3"

    return stage


def detect_weinstein_stage(df):

    close = df["Close"]

    ma10 = close.rolling(10).mean()
    ma30 = close.rolling(30).mean()
    ma40 = close.rolling(40).mean()

    price = close.iloc[-1]

    ma40_now = ma40.iloc[-1]
    ma40_prev = ma40.iloc[-5]

    slope40 = ma40_now - ma40_prev

    # ----------------------
    # Stage 2
    # ----------------------
    if price > ma40_now and slope40 > 0:

        base_high = df["High"].rolling(30).max().iloc[-2]

        if price > base_high:
            return "2A — Breakout 🚀"
        else:
            return "2B — Advancing Trend"

    # ----------------------
    # Stage 4
    # ----------------------
    if price < ma40_now and slope40 < 0:

        base_low = df["Low"].rolling(30).min().iloc[-2]

        if price < base_low:
            return "4A — Breakdown 🔻"
        else:
            return "4B — Declining"

    # ----------------------
    # Stage 1
    # ----------------------
    if abs(slope40) < ma40_now * 0.002:

        if price < ma40_now:
            return "1A — Bottoming"
        else:
            return "1B — Base Building"

    # ----------------------
    # Stage 3
    # ----------------------
    if price > ma40_now:
        return "3A — Topping"

    return "3B — Distribution"


def detect_base(df):

    recent = df.tail(20)

    high_range = recent["High"].max()
    low_range = recent["Low"].min()

    range_pct = (high_range - low_range) / low_range

    # ถ้าแกว่งไม่เกิน 15% ถือเป็น Base
    if range_pct < 0.15:
        return True

    return False


def detect_breakout(df):

    #recent = df.tail(20)
    recent = df.tail(21).iloc[:-1]  # ตัดแท่งล่าสุดออก

    resistance = recent["High"].max()
    latest = df.iloc[-1]

    if latest["Close"] > resistance:
        return True

    return False

    base_high = df["High"].rolling(30).max().iloc[-2]

    breakout = df["Close"].iloc[-1] > base_high





# ==========================================================
# ADD: Impulse MACD (LazyBear)
# ==========================================================
def calculate_impulse_macd(df: pd.DataFrame):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    # ===== Mean =====
    mean = (high + low + close) / 3

    period = 34
    alpha = 2 / (period + 1)

    # ===== SMMA =====
    smma_high = high.copy()
    smma_low = low.copy()

    for i in range(len(df)):
        if i == 0:
            smma_high.iloc[i] = high.iloc[i]
            smma_low.iloc[i] = low.iloc[i]
        else:
            smma_high.iloc[i] = (smma_high.iloc[i-1] * (period - 1) + high.iloc[i]) / period
            smma_low.iloc[i] = (smma_low.iloc[i-1] * (period - 1) + low.iloc[i]) / period

    # ===== ZLEMA =====
    ema1 = mean.copy()
    ema2 = mean.copy()

    for i in range(len(df)):
        if i == 0:
            ema1.iloc[i] = mean.iloc[i]
            ema2.iloc[i] = mean.iloc[i]
        else:
            ema1.iloc[i] = (mean.iloc[i] * alpha) + (ema1.iloc[i-1] * (1 - alpha))
            ema2.iloc[i] = (ema1.iloc[i] * alpha) + (ema2.iloc[i-1] * (1 - alpha))

    zlema = ema1 + (ema1 - ema2)

    # ===== MD =====
    md = pd.Series(index=df.index, dtype=float)

    for i in range(len(df)):
        if zlema.iloc[i] > smma_high.iloc[i]:
            md.iloc[i] = zlema.iloc[i] - smma_high.iloc[i]
        elif zlema.iloc[i] < smma_low.iloc[i]:
            md.iloc[i] = zlema.iloc[i] - smma_low.iloc[i]
        else:
            md.iloc[i] = 0

    # ===== SB =====
    sb = md.rolling(window=9).mean()

    # ===== SH =====
    sh = md - sb

    return md, sb, sh

# ===============================
# 📊 STAGE ANALYSIS ATTRIBUTES
# ===============================

def calculate_stage_attributes(symbol: str):
    data = yf.Ticker(symbol).history(period="2y")

    close = data["Close"]

    ma30 = close.rolling(30).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()

    mansfield = calculate_mansfield_rs(symbol)

    price = close.iloc[-1]
    high_52w = close.tail(252).max()

    slope200 = ma200.diff(20)

    stage = "Stage 1 / Base"

    if (
        price > ma30.iloc[-1] > ma150.iloc[-1] > ma200.iloc[-1]
        and slope200.iloc[-1] > 0
        and mansfield.iloc[-1] > 0
        and price > 0.75 * high_52w
    ):
        stage = "Stage 2 – Uptrend"

    elif price < ma200.iloc[-1]:
        stage = "Stage 4 – Downtrend"

    return {
        "data": data.tail(252),
        "ma30": ma30.tail(252),
        "ma150": ma150.tail(252),
        "ma200": ma200.tail(252),
        "mansfield": mansfield,
        "stage": stage
    }



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
# Extended Hours Price
# ==========================================================
def get_extended_hours(symbol):

    try:
        t = yf.Ticker(symbol)
        info = t.info

        pre = info.get("preMarketPrice")
        post = info.get("postMarketPrice")

        return pre, post

    except Exception:
        return None, None


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
        lines.append("Supports: " + ", ".join(f"{s['mid']:.0f}" for s in supports))
    if resistances:
        lines.append("Resistances: " + ", ".join(f"{r['mid']:.0f}" for r in resistances))
    return "\n".join(lines)


def ai_thesis_generator(symbol, price, ema50, ema100, ema200, rsi,
                        macd, signal, hist, supports, resistances):

    sr_text = _format_sr_for_prompt(supports, resistances)

    prompt = f"""
You are a professional fund manager.

Stock: {symbol}
Price: {price:.2f}

Market structure:
EMA levels: {ema50:.0f}, {ema100:.0f}, {ema200:.0f}

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

    # NEW
    pre_market, post_market = get_extended_hours(symbol)

    # =========================
    # Extended Hours Gap %
    # =========================
    pre_gap_pct = None
    post_gap_pct = None

    if pre_market:
        pre_gap_pct = (pre_market - price) / price * 100

    if post_market:
        post_gap_pct = (post_market - price) / price * 100

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
        "pre_market": pre_market,
        "post_market": post_market,
        "pre_gap_pct": pre_gap_pct,
        "post_gap_pct": post_gap_pct,
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
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema100 = close.ewm(span=100, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()


    # Momentum
    macd, signal, hist = calculate_macd(close)
    rsi = calculate_rsi(close)

    # Support / Resistance (ใช้ข้อมูล 1 ปี)
    price = close.iloc[-1]

    # ใช้ข้อมูล 1 ปี เหมือน cmd_sr
    data_sr = data_3y.tail(252)

    supports, resistances = calculate_support_resistance_zones(
        data_sr["High"].values,
        data_sr["Low"].values,
        price
    )

    # ✅ แสดงแค่ 2 ระดับใกล้ราคาที่สุด
    supports = supports[:2]
    resistances = resistances[:2]

    # ===== Last indicator values =====
    macd_last = macd.iloc[-1]
    signal_last = signal.iloc[-1]
    hist_last = hist.iloc[-1]
    rsi_last = rsi.iloc[-1]

    # แสดงเฉพาะ 1 เดือนล่าสุด
    data_1m = data_3y.tail(21)

    # =========================
    # Impulse MACD
    # =========================
    md_full, sb_full, sh_full = calculate_impulse_macd(data_3y)

    md = md_full.loc[data_1m.index]
    sb = sb_full.loc[data_1m.index]
    sh = sh_full.loc[data_1m.index]

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
    fig, (ax1, ax2, ax3, ax4) = plt.subplots(
        4, 1,
        figsize=(10, 12),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1, 1, 1.5]}
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

    # ===== Real Last Price =====
    real_close = data_1m["Close"].iloc[-1]

    # ===== Prevent price label overlap with SR =====
    label_y = real_close

    # รวมระดับ SR ทั้งหมด
    sr_levels = [s["mid"] for s in supports] + [r["mid"] for r in resistances]

    # กำหนด threshold ระยะห่าง (0.5% ของราคา)
    threshold = real_close * 0.005

    for level in sr_levels:
        if abs(label_y - level) < threshold:
            # ถ้าราคาอยู่เหนือ SR → ขยับขึ้น
            if real_close >= level:
                label_y += threshold
            # ถ้าอยู่ต่ำกว่า SR → ขยับลง
            else:
                label_y -= threshold

    # 👉 ใช้สีจากแท่ง Heikin Ashi ล่าสุด
    ha_open_last = ha["HA_Open"].iloc[-1]
    ha_close_last = ha["HA_Close"].iloc[-1]

    price_color = "#00E676" if ha_close_last >= ha_open_last else "#FF5252"

    # ===== Angled price line (L-shape) =====
    x_last = ha.index[-1]
    x_label = ha.index[-1] + pd.Timedelta(days=0.7)

    y_price = real_close

    # ระยะหักมุม (เล็กน้อย)
    x_mid = ha.index[-1] + pd.Timedelta(days=0.35)

    # เส้นแนวนอนช่วงแรก
    ax1.plot(
        [x_last, x_mid],
        [y_price, y_price],
        color=price_color,
        linewidth=1.2
    )

    # เส้นเฉียงไปยัง label
    ax1.plot(
        [x_mid, x_label],
        [y_price, y_price],
        color=price_color,
        linewidth=1.2
    )

    ax1.text(
        ha.index[-1] + pd.Timedelta(days=0.7),
        #real_close,
        label_y,
        f"{real_close:.2f}",
        #color="white",
        color="black",
        fontsize=7,
        #fontweight="bold",
        verticalalignment="center",
        horizontalalignment="left",
        bbox=dict(
            facecolor=price_color,
            edgecolor="none",
            boxstyle="round,pad=0.3"
        )
    )

    ax1.plot(ema50, label=f"EMA50 {ema50_last:.2f}",
             color="#2962FF", linewidth=1.2)

    ax1.plot(ema100, label=f"EMA100 {ema100_last:.2f}",
             color="#FF6D00", linewidth=1.2)

    ax1.plot(ema200, label=f"EMA200 {ema200_last:.2f}",
             color="#D50000", linewidth=1.6)

    # ===== Support =====
    for i, s in enumerate(supports, 1):
        y = s["mid"]

        ax1.axhline(
            y=y,
            color="#00E676",
            linestyle="--",
            linewidth=0.9,
            alpha=0.6,
            #label=f"S{i}: {y:.2f}"
        )

        # 🔹 แสดงตัวเลขบนเส้นด้านขวา
        ax1.text(
            #close.index[-1],
            close.index[-1] + pd.Timedelta(days=0.5),
            y,
            f"{y:.0f}",
            color="#00E676",
            fontsize=8,
            verticalalignment="center",
            horizontalalignment="left",
            bbox=dict(
                facecolor="#0e1117",
                edgecolor="none",
                alpha=0.8,
                boxstyle="round,pad=0.2"
            )

        )

    # ===== Resistance =====
    for i, r in enumerate(resistances, 1):
        y = r["mid"]

        ax1.axhline(
            y=y,
            color="#FF5252",
            linestyle=":",
            linewidth=0.9,
            alpha=0.6,
            #label=f"R{i}: {y:.2f}"
        )

        # 🔹 แสดงตัวเลขบนเส้นด้านขวา
        ax1.text(
            #close.index[-1],
            close.index[-1] + pd.Timedelta(days=0.5),
            y,
            f"{y:.0f}",
            color="#FF5252",
            fontsize=8,
            verticalalignment="center",
            horizontalalignment="left",
            bbox=dict(
                facecolor="#0e1117",
                edgecolor="none",
                alpha=0.8,
                boxstyle="round,pad=0.2"
            )
        )

    # ===== Legend Title =====
    legend1 = ax1.legend(
        loc="upper left",
        fontsize=9,
        frameon=True
    )

    legend1.get_frame().set_facecolor("#1c2128")  # พื้นหลังเข้ม
    legend1.get_frame().set_edgecolor("#2a2e39")  # ขอบ
    legend1.get_frame().set_alpha(0.9)            # ความทึบ
    legend1.get_frame().set_linewidth(0.8)
    legend1.get_frame().set_boxstyle("round,pad=0.4")

    ax1.set_title(
        f"{symbol} — Heikin Ashi Trend Structure",
        loc="left",
        fontsize=12,
        color="white"
)

    ax1.grid(True)


    # MACD
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

    #legend1 = ax2.legend(
    #loc="best",   # ← ให้ matplotlib เลือกตำแหน่งอัตโนมัติ
    #framealpha=0.15,
    #fontsize=9
    #)

    legend2 = ax2.legend(
        loc="upper left",
        fontsize=9,
        frameon=True
    )

    legend2.get_frame().set_facecolor("#1c2128")
    legend2.get_frame().set_edgecolor("#2a2e39")
    legend2.get_frame().set_alpha(0.9)
    legend2.get_frame().set_linewidth(0.8)
    legend2.get_frame().set_boxstyle("round,pad=0.4")

    ax2.grid(True)

    # =====================================
    # Impulse MACD (แทรกระหว่าง MACD กับ RSI)
    # =====================================
    impulse_colors = []
    for i in range(len(sh)):
        if sh.iloc[i] > 0:
            impulse_colors.append("#00E676")
        elif sh.iloc[i] < 0:
            impulse_colors.append("#FF5252")
        else:
            impulse_colors.append("#9E9E9E")

    # Histogram
    ax3.bar(
        sh.index,
        sh,
        color=impulse_colors,
        alpha=0.9,
        label=f"Impulse Histo {sh.iloc[-1]:+.3f}"
    )

    # MD + Signal
    #ax3.plot(md, label=f"MD {md.iloc[-1]:.3f}", linewidth=1.4)
    ax3.plot(md, color="#00B0FF", linewidth=1.6, label=f"MD {md.iloc[-1]:.3f}")
    #ax3.plot(sb, label=f"Signal (SB) {sb.iloc[-1]:.3f}", linestyle="--", linewidth=1.2)
    ax3.plot(sb, color="white", linestyle="--", linewidth=1.2, label=f"Signal (SB) {sb.iloc[-1]:.3f}")

    ax3.axhline(0, linewidth=1)

    legend_imp = ax3.legend(loc="upper left", fontsize=9, frameon=True)

    legend_imp.get_frame().set_facecolor("#1c2128")
    legend_imp.get_frame().set_edgecolor("#2a2e39")
    legend_imp.get_frame().set_alpha(0.9)
    legend_imp.get_frame().set_linewidth(0.8)

    ax3.set_title("Impulse MACD (ZLEMA)", loc="left", fontsize=10)
    ax3.grid(True)

    # RSI
    ax4.plot(rsi, label=f"RSI {rsi_last:.2f}",
         color="#AB47BC", linewidth=1.4)

    ax4.axhline(70, color="#FF5252", linestyle="--", alpha=0.5)
    ax4.axhline(30, color="#00E676", linestyle="--", alpha=0.5)

    ax4.set_ylim(0, 100)

    legend4 = ax4.legend(
        loc="upper left",
        fontsize=9,
        frameon=True
    )

    legend4.get_frame().set_facecolor("#1c2128")
    legend4.get_frame().set_edgecolor("#2a2e39")
    legend4.get_frame().set_alpha(0.9)
    legend4.get_frame().set_linewidth(0.8)
    legend4.get_frame().set_boxstyle("round,pad=0.4")
 
    ax4.grid(True)

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)

    return buf

def plot_impulse_chart(symbol: str):
    apply_tv_style()

    data = yf.Ticker(symbol).history(period="6mo")

    if data.empty or len(data) < 50:
        raise ValueError("NOT_ENOUGH_DATA")

    # ใช้ 1 เดือนล่าสุด
    data_1m = data.tail(21)

    md, sb, sh = calculate_impulse_macd(data)

    md = md.loc[data_1m.index]
    sb = sb.loc[data_1m.index]
    sh = sh.loc[data_1m.index]

    close = data["Close"].loc[data_1m.index]

    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=(10, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [2, 1]}
    )

    # ===== PRICE =====
    ax1.plot(close, color="white", linewidth=1.5, label="Price")
    ax1.set_title(f"{symbol} — Impulse MACD")
    ax1.legend(loc="upper left")
    ax1.grid(True)

    # ===== HISTO COLORS =====
    colors = []
    for i in range(len(sh)):
        #if sh.iloc[i] > 0:
        #    colors.append("#00E676")
        #elif sh.iloc[i] < 0:
        #    colors.append("#FF5252")
        #else:
        #    colors.append("#9E9E9E")
        if sh.iloc[i] > 0:
            impulse_colors.append("#00FF7F")  # เขียวสด
        elif sh.iloc[i] < 0:
            impulse_colors.append("#FF3B3B")  # แดงสด

    # ===== HISTOGRAM =====
    ax2.bar(sh.index, sh, color=colors, alpha=0.9, label="Impulse Histo")

    # ===== LINES =====
    ax2.plot(md, label="MD", linewidth=1.5)
    ax2.plot(sb, label="Signal (SB)", linestyle="--", linewidth=1.2)

    ax2.axhline(0, linewidth=1)

    ax2.set_title("Impulse MACD (ZLEMA)")
    ax2.legend(loc="upper left")
    ax2.grid(True)

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)

    return buf
    
# ==========================================================
# Stage Analysis - Mansfield RS Plot
# ==========================================================
def plot_stage_rs(symbol: str):
    apply_tv_style()

    df = calculate_mansfield_rs(symbol)

    fig, ax = plt.subplots(figsize=(10, 5))

    # RS Line (black in Pine → white here for dark bg)
    ax.plot(df.index, df["rs"], color="white", linewidth=1.5, label="Stock / Index")

    # MA Line (blue)
    ax.plot(df.index, df["rs_ma"], color="#2962FF", linewidth=1.2, label="MA 52W")

    ax.set_title(f"{symbol} — Mansfield RS (Weekly)", loc="left")
    ax.legend(loc="upper left")
    ax.grid(True)

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)

    return buf

# ==========================================================
# SATA PLOT
# ==========================================================
def plot_sata(symbol: str):
    apply_tv_style()

    rs_df = calculate_mansfield_rs(symbol)
    df, sata, rs = calculate_sata(symbol)

    latest_score = int(sata["score"].iloc[-1])

    stage_label = detect_stage_pro(df, sata)
    is_base = detect_base(df)
    is_breakout = detect_breakout(df)

    latest_score = sata["score"].iloc[-1]

    # ===============================
    # ADVANCED PRO+ LOGIC
    # ===============================

    volume_contraction = detect_volume_contraction(df)

    base_high = df["High"].rolling(30).max().iloc[-2]
    breakout = df["Close"].iloc[-1] > base_high

    breakout_volume = detect_breakout_volume(df, base_high)

    rs_new_high = detect_rs_new_high(rs)

    stage_transition = detect_stage_transition(df)

    strong_stage2 = detect_strong_stage2(latest_score, breakout_volume)

    # ===== จำกัดช่วงเวลาแสดงผลย้อนหลัง 1 ปี =====
    end_date = rs_df.index.max()
    start_date = end_date - pd.DateOffset(years=1)

    rs_df = rs_df[rs_df.index >= start_date]
    sata = sata[sata.index >= start_date]

    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=(12, 7),
        sharex=True,
        gridspec_kw={"height_ratios": [2, 1]}
    )

    # ===== MAIN TITLE =====
    plt.tight_layout(rect=[0, 0, 1, 0.95])

    left = fig.subplotpars.left

    fig.text(
        left,
        0.98,
        f"{symbol} — Stage Analysis",
        ha="left",
        va="top",
        fontsize=16,
        fontweight="bold",
        color="white"
    )

    # ===== Panel 1: Mansfield RS =====
    ax1.plot(rs_df.index, rs_df["rs"], color="#00E5FF", linewidth=1.8)
    ax1.plot(rs_df.index, rs_df["rs_ma"], linestyle="--", color="#9E9E9E", linewidth=1.4, alpha=0.8)

    # RS BASELINE (StageAnalysis style)
    ax1.axhline(0, color="#607D8B", linestyle="--", linewidth=1)

    # ===== AUTO SCALE RS =====
    rs_min = min(rs_df["rs"].min(), rs_df["rs_ma"].min())
    rs_max = max(rs_df["rs"].max(), rs_df["rs_ma"].max())

    padding = (rs_max - rs_min) * 0.15
    ax1.set_ylim(rs_min - padding, rs_max + padding)

    ax1.margins(x=0)

    ax1.set_ylabel("RS Value")

    ax1.axhline(0, linestyle="--", alpha=0.5)
    #ax1.set_title("Mansfield Relative Strength", loc="left", fontsize=11, fontweight="bold")
    ax1.set_title("Mansfield Relative Strength", loc="left", fontsize=11)
    ax1.grid(True)

    # ===== Panel 2: SATA Score =====
    ax2.plot(sata.index, sata["score"], color="#FFD700", linewidth=1.6)

    ax2.axhline(6, linestyle="--", color="#00E676", linewidth=1)
    ax2.axhline(3, linestyle="--", color="#FF5252", linewidth=1)

    ax2.set_ylabel("Score")

    ax2.set_ylim(0, 10)
    #ax2.set_title("SATA Score", loc="left", fontsize=11, fontweight="bold")
    ax2.set_title("SATA Score", loc="left", fontsize=11)
    ax2.grid(True)

    # COMMON STYLE
    for ax in [ax1, ax2]:

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.35)

        # remove side padding (กราฟชิดขอบ)
        ax.margins(x=0)


    # EXPORT PNG (Telegram optimized)
    buf = io.BytesIO()
    #plt.tight_layout()
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)

    return buf

# ==========================================================
# Telegram Handlers
# ==========================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        START_TEXT,
        reply_markup=main_menu_keyboard()
    )

# ==========================================================
# CALLBACK MENU
# ==========================================================
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    #await query.answer()

    try:
        await query.answer()
    except BadRequest:
        pass

    data = query.data

    if data == "menu_ta":
        context.user_data["mode"] = "ta"
        await query.message.reply_text("🔎 พิมพ์สัญลักษณ์หุ้น เช่น `AAPL`")

    elif data == "menu_ai":
        context.user_data["mode"] = "ai"
        await query.message.reply_text("🤖 พิมพ์สัญลักษณ์หุ้น เช่น `MSFT`")

    elif data == "menu_sr":
        context.user_data["mode"] = "sr"
        await query.message.reply_text("📐 พิมพ์สัญลักษณ์หุ้น เช่น `NVDA`")

    elif data == "menu_ch":
        context.user_data["mode"] = "ch"
        await query.message.reply_text("📈 พิมพ์สัญลักษณ์หุ้น เช่น `PLTR`")

    elif data == "menu_impulse":
        context.user_data["mode"] = "impulse"
        await query.message.reply_text("⚡ พิมพ์สัญลักษณ์หุ้น เช่น `TSLA`")

    elif data == "menu_man":
        context.user_data["mode"] = "man"
        await query.message.reply_text("📊 พิมพ์สัญลักษณ์หุ้น เช่น `AAPL`")

    elif data == "menu_stage":
        context.user_data["mode"] = "stage"
        await query.message.reply_text("📊 พิมพ์สัญลักษณ์หุ้น เช่น `AAPL`")

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

    elif data.startswith("again_man:"):
        symbol = data.split(":")[1]
        context.args = [symbol]
        await cmd_man(query, context)

    elif data.startswith("again_stage:"):
        symbol = data.split(":")[1]
        context.args = [symbol]
        await cmd_stage(query, context)

# ==========================================================
# TEXT ROUTER (เพิ่ม impulse)
# ==========================================================
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
    elif mode == "man":
        await cmd_man(update, context)

    elif mode == "stage":
        await cmd_stage(update, context)

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

    pre_text = "-"
    post_text = "-"

    if d["pre_market"]:
        gap = f" ({d['pre_gap_pct']:+.2f}%)" if d["pre_gap_pct"] else ""
        pre_text = f"${d['pre_market']:.2f}{gap}"

    if d["post_market"]:
        gap = f" ({d['post_gap_pct']:+.2f}%)" if d["post_gap_pct"] else ""
        post_text = f"${d['post_market']:.2f}{gap}"

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

    #text = (
    #    f"📊 {symbol}\n"
    #    f"💵 ราคา: ${d['price']:.2f} ({d['change_pct']:+.2f}%)\n\n"

    text = (
        f"📊 {symbol}\n"
        f"💵 ราคา: ${d['price']:.2f} ({d['change_pct']:+.2f}%)\n"
        f"🌅 ราคาก่อนตลาดเปิด: {pre_text}\n"
        f"🌙 ราคาหลังตลาดปิด: {post_text}\n\n"
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

async def cmd_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0].upper()
    context.user_data["last_symbol"] = symbol

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

async def cmd_sr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0].upper()
    context.user_data["last_symbol"] = symbol

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
            text += f"  • {s['mid']:.0f} (↓ {dist:.2f}%) | S={s['strength']}\n"
    else:
        text += "  • ไม่มีระดับที่ชัดเจน\n"

    text += "\n🔴 Resistance Zones\n"
    if resistance:
        for r in resistance:
            dist = (r["mid"] - price) / price * 100
            text += f"  • {r['mid']:.0f} (↑ {dist:.2f}%) | S={r['strength']}\n"
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
    context.user_data["last_symbol"] = symbol

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

async def cmd_man(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0].upper()
    context.user_data["last_symbol"] = symbol

    try:
        chart = plot_stage_rs(symbol)
    except Exception:
        await update.message.reply_text("❌ ไม่สามารถสร้างกราฟ Stage RS ได้")
        return

    await update.message.reply_photo(
        photo=chart,
        caption=f"📊 {symbol} — Mansfield RS",
        reply_markup=post_result_keyboard(symbol)
    )

# ===============================
# ADVANCED PRO+ DETECTION ENGINE
# ===============================

def detect_volume_contraction(df, lookback=20):
    recent_vol = df["Volume"].tail(lookback)
    return recent_vol.mean() < df["Volume"].rolling(50).mean().iloc[-1]

def detect_breakout_volume(df, breakout_level):
    latest_vol = df["Volume"].iloc[-1]
    avg_vol = df["Volume"].rolling(50).mean().iloc[-1]
    price_breakout = df["Close"].iloc[-1] > breakout_level
    volume_expansion = latest_vol > avg_vol * 1.5
    return price_breakout and volume_expansion

def detect_rs_new_high(rs_series, lookback=60):
    recent_high = rs_series.tail(lookback).max()
    return rs_series.iloc[-1] >= recent_high

def detect_stage_transition(df):
    ma50 = df["Close"].rolling(50).mean()
    ma200 = df["Close"].rolling(200).mean()

    if ma50.iloc[-1] > ma200.iloc[-1] and ma50.iloc[-20] <= ma200.iloc[-20]:
        return "Stage 1 ➜ Stage 2"

    if ma50.iloc[-1] < ma200.iloc[-1] and ma50.iloc[-20] >= ma200.iloc[-20]:
        return "Stage 3 ➜ Stage 4"

    return None

def detect_strong_stage2(score, breakout):
    return score >= 8 and breakout

async def cmd_stage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0].upper()
    context.user_data["last_symbol"] = symbol

    try:
        # ===== เรียกข้อมูล SATA =====
        df, sata, rs = calculate_sata(symbol)

        latest_score = int(sata["score"].iloc[-1])
        stage_label = detect_weinstein_stage(df)
        is_base = detect_base(df)
        is_breakout = detect_breakout(df)

        # ===== สร้างกราฟ =====
        chart = plot_sata(symbol)

    except Exception as e:
        await update.message.reply_text(f"❌ ไม่สามารถสร้างกราฟ SATA ได้\n{str(e)}")
        return

    # ===============================
    # ADVANCED PRO+ LOGIC
    # ===============================

    volume_contraction = detect_volume_contraction(df)

    base_high = df["High"].rolling(30).max().iloc[-2]

    breakout = df["Close"].iloc[-1] > base_high

    breakout_volume = detect_breakout_volume(df, base_high)

    rs_new_high = detect_rs_new_high(rs)

    stage_transition = detect_stage_transition(df)

    strong_stage2 = detect_strong_stage2(latest_score, breakout)

    caption_text = f"""
    🚀 {symbol} — Stage Analysis

    Stage: {stage_label}

    SATA Score: {latest_score}/10
    Base Forming: {"Yes" if is_base else "No"}
    Breakout: {"Yes 🚀" if is_breakout else "No"}

    Volume Contraction: {"Yes 📉" if volume_contraction else "No"}
    Breakout Volume >150%: {"Yes 🔥" if breakout_volume else "No"}
    RS New High: {"Yes 💪" if rs_new_high else "No"}

    Stage Transition: {stage_transition if stage_transition else "None"}
    Strong Stage 2: {"YES 🚀🔥" if strong_stage2 else "No"}
    """

    #await update.message.reply_photo(
    #    photo=chart,
    #    caption=caption_text
    #)

    await update.message.reply_photo(
        photo=chart,
        caption=caption_text,
        #caption=f"📊 {symbol} — Stage Analysis",
        reply_markup=post_result_keyboard(symbol)
    )

# ==========================================================
# IMACD SCAN COMMANDS (/im1 /im2)
# ==========================================================
async def cmd_im1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 กำลังสแกน Impulse GREEN 1–2 วัน ...")

    symbols = get_all_symbols()
    await run_scan(update, symbols, min_streak=3, mode="below", title="🆕 Impulse GREEN Streak 1–2 วัน")

async def cmd_im2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 กำลังสแกน Impulse GREEN ≥ 3 วัน ...")

    symbols = get_all_symbols()
    await run_scan(update, symbols, min_streak=3, mode="above", title="🚀 Impulse GREEN Streak ≥ 3 วัน")

async def cmd_stage_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbols = context.user_data.get("symbols")

    results = scan_stage2_market(symbols)

    if not results:
        await update.message.reply_text("❌ ไม่พบหุ้น Stage 2")
        return

    import math

    chunk = 20
    pages = math.ceil(len(results) / chunk)

    for p in range(pages):

        part = results[p*chunk:(p+1)*chunk]

        text = f"🚀 Strong Stage 2 Scan ({p+1}/{pages})\n\n"

        if p == 0:
            text += f"พบทั้งหมด {len(results)} หุ้น\n\n"

        for r in part:

            text += (
                f"🟢 {r['symbol']} "
                f"| Score {r['score']}/10 "
                f"| ${r['price']:.2f}"
            )

            # breakout signal
            if r["breakout"]:
                text += " | 🚀"
            else:
                text += ""

            # RS signal
            if r["rs"]:
                text += " | RS↑"

            text += "\n"

            attrs = [
                r["a1"], r["a2"], r["a3"], r["a4"], r["a5"],
                r["a6"], r["a7"], r["a8"], r["a9"], r["a10"]
            ]

            attr_text = "".join(["✅" if x == 1 else "❌" for x in attrs])

            text += f"   SATA: {attr_text}\n"

        if p == pages - 1:

            await update.message.reply_text(
                text,
                reply_markup=main_menu_keyboard()
            )

        else:
            await update.message.reply_text(text)

def count_green_streak(sh_series: pd.Series) -> int:
    streak = 0
    #for val in reversed(sh_series):
    for val in sh_series.iloc[::-1]:
        if val > 0:
            streak += 1
        else:
            break
    return streak

def get_sp500_symbols():
    import pandas as pd

    url = "https://datahub.io/core/s-and-p-500-companies/r/constituents.csv"
    df = pd.read_csv(url)

    symbols = df["Symbol"].dropna().tolist()
    symbols = [str(s).replace(".", "-") for s in symbols]

    return symbols

def get_nasdaq100_symbols():

    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, headers=headers)
    tables = pd.read_html(StringIO(r.text))

    df = tables[4]

    symbols = [s.replace(".", "-") for s in df["Ticker"].dropna()]
    return symbols

def get_all_symbols():
    """
    รวมสองตลาด + ลบตัวซ้ำ
    """
    sp500 = get_sp500_symbols()
    nasdaq = get_nasdaq100_symbols()

    symbols = list(set(sp500 + nasdaq))

    #print(f"Loaded symbols: {len(symbols)} ตัว")
    print(f"Loaded symbols: {len(symbols)} ตัว", flush=True)

    return symbols

def scan_impulse_green_streak(
    symbols: list,
    min_streak: int = 3,
    lookback_months: int = 3,
    mode: str = "above"  # "above" หรือ "below"
):
    results = []

    for symbol in symbols:
        try:
            data = yf.Ticker(symbol).history(
                period=f"{lookback_months}mo"
            )

            if data.empty or len(data) < 50:
                continue

            md, sb, sh = calculate_impulse_macd(data)

            streak = count_green_streak(sh.dropna())

            # ✅ เงื่อนไขใหม่
            if (mode == "above" and streak >= min_streak) or \
               (mode == "below" and 1 <= streak < min_streak):


                results.append({
                    "symbol": symbol,
                    "streak": streak,
                    "price": data["Close"].iloc[-1]
                })

        except:
            continue

    # 🔽 เรียงน้อย → มาก
    results = sorted(results, key=lambda x: x["streak"])

    return results

# ==========================================================
# STAGE SCAN ENGINE
# ==========================================================
def scan_stage2_market(symbols):

    results = []

    for symbol in symbols:

        try:

            df, sata, rs = calculate_sata(symbol)

            if len(df) < 100:
                continue

            latest_score = sata["score"].iloc[-1]

            stage = detect_stage_pro(df, sata)

            base = detect_base(df)

            breakout = detect_breakout(df)

            rs_new_high = detect_rs_new_high(rs)

            strong_stage2 = detect_strong_stage2(latest_score, breakout)

            # ===== เงื่อนไข Stage 2 Screener =====
            #if stage == "Stage 2" and strong_stage2:
            #if stage == "Stage 2":
            #if stage == strong_stage2:
            #if stage == breakout:
            if stage == "Stage 2" and latest_score >= 6:

                price = df["Close"].iloc[-1]

                latest_attr = sata.iloc[-1]

                results.append({
                    "symbol": symbol,
                    "score": int(latest_score),
                    "price": price,
                    "breakout": breakout,
                    "rs": rs_new_high,

                    # SATA Attributes
                    "a1": int(latest_attr["a1"]),
                    "a2": int(latest_attr["a2"]),
                    "a3": int(latest_attr["a3"]),
                    "a4": int(latest_attr["a4"]),
                    "a5": int(latest_attr["a5"]),
                    "a6": int(latest_attr["a6"]),
                    "a7": int(latest_attr["a7"]),
                    "a8": int(latest_attr["a8"]),
                    "a9": int(latest_attr["a9"]),
                    "a10": int(latest_attr["a10"]),
                })

        except:
            continue

    # เรียงจาก SATA Score สูงสุด
    results = sorted(results, key=lambda x: x["score"], reverse=True)

    return results

async def run_scan(update_or_query, symbols, min_streak, mode, title):

    # ✅ แยก message กับ callback ให้ชัด
    if hasattr(update_or_query, "message"):  
        # มาจาก callback_query
        msg = update_or_query.message
    else:
        # มาจาก update.message
        msg = update_or_query.message

    #await msg.reply_text("🔍 กำลังสแกนตลาด. กรุณารอ")

    try:
        results = scan_impulse_green_streak(
            symbols,
            min_streak=min_streak,
            mode=mode
        )

        if not results:
            await msg.reply_text("❌ ไม่พบหุ้นตามเงื่อนไข")
            return

        import math

        chunk_size = 20
        total_items = len(results)
        total_pages = math.ceil(total_items / chunk_size)

        for page in range(total_pages):
            start = page * chunk_size
            end = start + chunk_size
            chunk = results[start:end]

            text = f"{title} ({page+1}/{total_pages})\n"

            if page == 0:
                text += f"จำนวนทั้งหมด {total_items} หุ้น\n"

            text += "\n"

            for r in chunk:
                text += (
                    f"🟢 {r['symbol']}  "
                    f"| {r['streak']} วัน "
                    f"| ${r['price']:.2f}\n"
                )

            # ✅ เฉพาะหน้าสุดท้าย ใส่เมนู
            if page == total_pages - 1:
                await msg.reply_text(
                    text,
                    reply_markup=main_menu_keyboard()
                )
            else:
                await msg.reply_text(text)

    except Exception as e:
        await msg.reply_text(f"❌ scan error: {str(e)}")

# ==========================================================
# App Bootstrap
# ==========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

# ==========================================================
# REGISTER HANDLER (เพิ่มบรรทัดนี้)
# ==========================================================
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

    app.add_handler(CommandHandler("man", cmd_man))
    app.add_handler(CommandHandler("stage", cmd_stage))

    app.run_polling()


if __name__ == "__main__":
    main()
