import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from pydub import AudioSegment
from io import BytesIO

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎧 Salom! MP3 fayl yubor — men unga effekt qo‘shaman (Zal, Bass, 8D)!")

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.audio:
        await update.message.reply_text("📁 Iltimos, MP3 fayl yubor.")
        return

    file = await update.message.audio.get_file()
    file_path = await file.download_to_drive("temp.mp3")

    # Audio faylni o‘qish
    audio = AudioSegment.from_mp3("temp.mp3")

    # Effekt turi (tasodifiy yoki tanlanadigan)
    effect_type = "Zal"  # Keyin tanlanadigan qilish mumkin

    if effect_type == "Zal":
        processed = audio.fade_in(2000).fade_out(2000)
    elif effect_type == "Bass":
        processed = audio.low_pass_filter(200)
    elif effect_type == "8D":
        processed = audio.pan(-0.5)

    processed.export("processed.mp3", format="mp3")

    await update.message.reply_audio(audio=open("processed.mp3", "rb"), caption=f"✅ Effekt qo‘shildi: {effect_type}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.run_polling()

if __name__ == "__main__":
    main()
