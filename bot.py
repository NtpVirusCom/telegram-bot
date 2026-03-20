# ==========================================================
# Imports & Config
# ==========================================================
import io
import logging
import matplotlib.pyplot as plt
import math
import os
import pandas as pd

import yfinance as yf


from openai import OpenAI
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, filters, MessageHandler


# ==========================================================
# MODIFY MENU
# ==========================================================
def main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🔍 IMACD 1–2 วัน", callback_data="menu_im1"),
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
            InlineKeyboardButton("🔍 IMACD 1–2 วัน", callback_data="menu_im1"),
            InlineKeyboardButton("🔍 Stage 2", callback_data=f"again_stage_scan:{symbol}"),
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
    await query.answer()

    data = query.data

    if data == "menu_im1":
        await query.message.reply_text("🔎 กำลังสแกน Impulse GREEN 1–2 วัน ...")
        symbols = get_all_symbols()
        context.user_data["mode"] = "im1"        
        #print(f"Loaded symbols: {len(symbols)} ตัว", flush=True)
        #print(f"Loaded symbols: {len(symbols)} ตัว")
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
def detect_rs_new_high(rs_series, lookback=60):
    recent_high = rs_series.tail(lookback).max()
    return rs_series.iloc[-1] >= recent_high

def detect_strong_stage2(score, breakout):
    return score >= 8 and breakout

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
                text += " 🚀 Breakout"
            else:
                text += " | No Breakout"

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
    import pandas as pd

    #url = "https://datahub.io/core/nasdaq-listings/r/nasdaq-listed-symbols.csv"
    url = "https://raw.githubusercontent.com/Gary-Strauss/NASDAQ100_Constituents/master/data/nasdaq100_constituents.csv"
    df = pd.read_csv(url)

    # ✅ ลบ NaN ออกก่อน
    symbols = df["Ticker"].dropna().tolist()

    # ✅ แปลงเป็น string กันพัง
    symbols = [str(s).replace(".", "-") for s in symbols]

    #return symbols[:100]
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

        #import math

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
