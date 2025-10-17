# bot.py
from dotenv import load_dotenv
import os
import requests
import ffmpeg  # requires ffmpeg binary installed on the server
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from serpapi import GoogleSearch

# Load environment variables from .env
load_dotenv()

BOT_TOKEN = os.getenv("8242387447:AAELsLQ73nI7Toby14MbIj1Gf1V8QpJFq6M")        # <- put your real token in .env
SERPAPI_KEY = os.getenv("3a43606ac3d94fd4a87f93546eeba9edd0664e7c9337547bde52afed574c6767")    # <- put your real SerpAPI key in .env

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in environment (.env).")
if not SERPAPI_KEY:
    raise RuntimeError("SERPAPI_KEY is not set in environment (.env).")

# In-memory stores (for simple usage). For production, use persistent storage.
user_files = {}
search_results = {}
user_keyboards = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 Salom! Menga qo'shiq yoki ijrochi nomini yozing.\n"
        "Men Google orqali 10 ta variant topaman va siz tanlaysiz."
    )

async def search_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Called when user sends plain text (not command)
    query = update.message.text.strip()
    user_id = update.message.from_user.id

    await update.message.reply_text(f"🔎 '{query}' uchun qidirilmoqda... Iltimos kuting.")

    params = {
        "engine": "google",
        "q": f"{query} filetype:mp3",
        "num": "10",
        "api_key": SERPAPI_KEY
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        links = results.get("organic_results", []) or results.get("results", [])

        if not links:
            # fallback: create demo variants (so bot remains responsive)
            await update.message.reply_text("⚠️ Onlayn mp3 topilmadi. Demo variantlar yuborildi.")
            variants = [f"{query} Variant {i+1}" for i in range(10)]
            keyboard = [[InlineKeyboardButton(v, callback_data=f"demo__{i}")] for i,v in enumerate(variants)]
            # store demo info
            search_results[user_id] = {str(i): {"title": variants[i], "url": None} for i in range(10)}
            user_keyboards[user_id] = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("🎶 Quyidagi variantlardan birini tanlang:", reply_markup=user_keyboards[user_id])
            return

        keyboard = []
        user_search = {}
        count = 0
        for i, item in enumerate(links):
            if count >= 10:
                break
            # item may have different keys depending on SerpAPI response
            mp3_url = item.get("link") or item.get("url") or item.get("source") or None
            title = item.get("title") or item.get("name") or f"Variant {i+1}"
            if not mp3_url:
                continue
            # store by index string
            key = str(count)
            user_search[key] = {"title": title, "url": mp3_url}
            keyboard.append([InlineKeyboardButton(title[:60], callback_data=key)])
            count += 1

        if not user_search:
            await update.message.reply_text("❌ Mp3 havolalari topilmadi. Iltimos boshqa so‘rov kiriting.")
            return

        search_results[user_id] = user_search
        reply_markup = InlineKeyboardMarkup(keyboard)
        user_keyboards[user_id] = reply_markup
        await update.message.reply_text("🎶 Quyidagi variantlardan birini tanlang:", reply_markup=reply_markup)

    except Exception as e:
        await update.message.reply_text(f"❌ Qidiruvda xatolik: {str(e)}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # CallbackQuery handler for inline buttons
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    choice = query.data

    keyboard = user_keyboards.get(user_id)

    # handle demo choice prefix
    if choice.startswith("demo__"):
        idx = choice.split("__", 1)[1]
        title = f"Demo Variant {int(idx)+1}"
        # demo audio URL (royalty-free) - used if no real mp3 was found
        demo_url = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"
        mp3_info = {"title": title, "url": demo_url}
    else:
        if user_id not in search_results or choice not in search_results[user_id]:
            await query.edit_message_text("⚠️ Noto'g'ri tanlov.", reply_markup=keyboard)
            return
        mp3_info = search_results[user_id][choice]

    mp3_url = mp3_info.get("url")
    title = mp3_info.get("title", "Unknown")

    local_file = f"{user_id}_original.mp3"

    try:
        await query.edit_message_text(f"⬇️ '{title}' yuklanmoqda...", reply_markup=keyboard)

        if not mp3_url:
            await query.edit_message_text("❌ Mp3 URL topilmadi. Iltimos boshqa variant tanlang.", reply_markup=keyboard)
            return

        # Download with streaming and size checks
        r = requests.get(mp3_url, stream=True, timeout=30, allow_redirects=True)
        if r.status_code != 200:
            await query.edit_message_text(f"❌ Havolani ochib bo'lmadi (status: {r.status_code}).", reply_markup=keyboard)
            return

        content_type = r.headers.get('content-type', '').lower()
        if ('audio' not in content_type) and ('mp3' not in content_type) and ('mpeg' not in content_type) and ('octet-stream' not in content_type):
            # still allow if content-type absent; but warn
            # proceed but check size and smallness later
            pass

        content_length = r.headers.get('content-length')
        if content_length and int(content_length) > 50 * 1024 * 1024:
            await query.edit_message_text("❌ Fayl juda katta (max 50MB). Iltimos, boshqa variant tanlang.", reply_markup=keyboard)
            r.close()
            return

        total_size = 0
        max_size = 50 * 1024 * 1024
        with open(local_file, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    total_size += len(chunk)
                    if total_size > max_size:
                        f.close()
                        if os.path.exists(local_file):
                            os.remove(local_file)
                        await query.edit_message_text("❌ Fayl juda katta (max 50MB). Iltimos, boshqa variant tanlang.", reply_markup=keyboard)
                        return
                    f.write(chunk)

        if total_size < 1000:
            if os.path.exists(local_file):
                os.remove(local_file)
            await query.edit_message_text("❌ Fayl juda kichik – bu audio emas. Iltimos boshqa variant tanlang.", reply_markup=keyboard)
            return

        user_files[user_id] = local_file
        await query.edit_message_text("✅ Yuklandi! Original audio yuborilmoqda...", reply_markup=keyboard)
        # send original file
        await context.bot.send_audio(chat_id=user_id, audio=open(local_file, "rb"), title=title)
        await context.bot.send_message(chat_id=user_id,
            text="✅ Muvaffaqiyatli yuklandi! Endi effekt tanlang:\n/zal — Zal effekti\n/bass — Bass effekti\n/8d — 8D effekti"
        )

    except requests.exceptions.Timeout:
        await query.edit_message_text("❌ Yuklash vaqti tugadi (timeout). Iltimos boshqa variant tanlang.", reply_markup=keyboard)
    except Exception as e:
        if os.path.exists(local_file):
            os.remove(local_file)
        await query.edit_message_text(f"❌ Yuklashda xatolik: {str(e)[:200]}", reply_markup=keyboard)

async def apply_effect(update: Update, context: ContextTypes.DEFAULT_TYPE, effect_type):
    user_id = update.message.from_user.id
    if user_id not in user_files:
        await update.message.reply_text("⚠️ Avval qo'shiq yuklang!")
        return

    input_file = user_files[user_id]
    output_file = f"{user_id}_{effect_type}.mp3"
    await update.message.reply_text(f"🎚 {effect_type.upper()} effekti yaratilmoqda...")

    try:
        # Using ffmpeg-python (https://github.com/kkroening/ffmpeg-python)
        if effect_type == "zal":
            # aecho as reverb demo
            (
                ffmpeg
                .input(input_file)
                .output(output_file, af='aecho=0.8:0.9:1000:0.3')
                .overwrite_output()
                .run()
            )
        elif effect_type == "bass":
            # bass boost using lowpass and volume as simple example
            (
                ffmpeg
                .input(input_file)
                .output(output_file, af='bass=g=10')
                .overwrite_output()
                .run()
            )
        elif effect_type == "8d":
            # apulsator effect (works if ffmpeg has apulsator)
            (
                ffmpeg
                .input(input_file)
                .output(output_file, af='apulsator=hz=0.125')
                .overwrite_output()
                .run()
            )

        await update.message.reply_audio(audio=open(output_file, "rb"), title=f"{effect_type.upper()} versiya")
        # cleanup effect file (keep original if desired)
        if os.path.exists(output_file):
            os.remove(output_file)

    except Exception as e:
        await update.message.reply_text(f"❌ Effektda xatolik: {e}")

async def zal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await apply_effect(update, context, "zal")

async def bass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await apply_effect(update, context, "bass")

async def _8d(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await apply_effect(update, context, "8d")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("zal", zal))
    app.add_handler(CommandHandler("bass", bass))
    app.add_handler(CommandHandler("8d", _8d))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_music))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🎶 Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
