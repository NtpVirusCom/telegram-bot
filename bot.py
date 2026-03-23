# ========================================================v.141==
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
            InlineKeyboardButton("🔍 Impulse MACD", callback_data="menu_im1"),
            InlineKeyboardButton("🔍 Stage 2", callback_data="menu_stage_scan"),
        ],
        [
            InlineKeyboardButton("📖 Command Guide", callback_data="menu_help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def post_result_keyboard(symbol: str):
    keyboard = [
        [
            InlineKeyboardButton("🔍 Impulse MACD", callback_data="menu_im1"),
            InlineKeyboardButton("🔍 Stage 2", callback_data="menu_stage_scan"),
        ],
        [
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

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
# Mansfield RS (StageAnalysis - Weekly, Unflattened)
# ==========================================================
def calculate_mansfield_rs(symbol: str, benchmark: str = "^GSPC", ma_length: int = 52):
    """
    Pine reference:
    stockDividedBySpx = stock / spx * 100
    zeroLine = ta.sma(stockDividedBySpx, maLength)

    Weekly resolution
    """

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

# ==========================================================
# Chart Style (Bloomberg / TradingView)
# ==========================================================
# ==========================================================
# SATA PLOT
# ==========================================================
def plot_sata(symbol: str):
    apply_tv_style()

    rs_df = calculate_mansfield_rs(symbol)
    #df, sata = calculate_sata(symbol)
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
    #strong_stage2 = detect_strong_stage2(latest_score, is_breakout)


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

    if data == "menu_im1":
        await query.message.reply_text("🔎 กำลังสแกน Impulse GREEN 1–2 วัน ...")
        symbols = get_all_symbols()
        context.user_data["mode"] = "im1"        
        await run_scan(query, symbols, min_streak=3, mode="below", title="🆕 Impulse GREEN Streak 1–2 วัน")

    elif data == "menu_stage_scan":
        await query.message.reply_text("🔎 กำลังสแกน Stage 2 ทั้งตลาด...")
        symbols = get_all_symbols()
        context.user_data["symbols"] = symbols
        await cmd_stage_scan(query, context)

    elif data == "menu_help":
        await query.message.reply_text(HELP_TEXT)

    elif data == "menu_home":
        await query.message.reply_text(
            START_TEXT,
            reply_markup=main_menu_keyboard()
        )

# ==========================================================
# TEXT ROUTER (เพิ่ม impulse)
# ==========================================================
async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    if not mode:
        return

    symbol = update.message.text.strip().upper()
    context.args = [symbol]

    if mode == "im1":
        await cmd_im1(update, context)

    elif mode == "stage2scan":
        await cmd_stage_scan(update, context)
    
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)
    context.user_data["last_symbol"] = symbol

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
        #stage_label = detect_stage_pro(df, sata)
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

async def cmd_stage_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):

    #await update.message.reply_text("🔎 กำลังสแกน Stage 2 ทั้งตลาด...")

    symbols = context.user_data.get("symbols")

    results = scan_stage2_market(symbols)

    if not results:
        await update.message.reply_text("❌ ไม่พบหุ้น Stage 2")
        return

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
        msg = update_or_query.message
    else:
        msg = update_or_query.message

    try:
        results = scan_impulse_green_streak(
            symbols,
            min_streak=min_streak,
            mode=mode
        )

        if not results:
            await msg.reply_text("❌ ไม่พบหุ้นตามเงื่อนไข")
            return

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

    app.add_handler(CommandHandler("im1", cmd_im1))
    app.add_handler(CommandHandler("stage2scan", cmd_stage_scan))

    app.run_polling()


if __name__ == "__main__":
    main()
