import os
import time
import logging
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from google import genai
from gtts import gTTS

# កំណត់ Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ទាញយក Token ពី Environment Variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("សូមកំណត់ TELEGRAM_BOT_TOKEN ក្នុង Environment Variables!")
if not GEMINI_API_KEY:
    raise ValueError("សូមកំណត់ GEMINI_API_KEY ក្នុង Environment Variables!")

ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Flask Server សម្រាប់រក្សា Render ឱ្យដំណើរការ 24/7
app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Direct Video Translator Bot is running successfully!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Command /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🎬 **ស្វាគមន៍មកកាន់ Direct Video Translator Bot!**\n\n"
        "វិធីប្រើប្រាស់៖\n"
        "1. ផ្ញើវីដេអូមកទីនេះដោយផ្ទាល់\n"
        "2. ជ្រើសរើសភាសា (ខ្មែរ, អង់គ្លេស, ឬ ថៃ)\n"
        "3. ជ្រើសរើសប្រភេទសំឡេង (ស្រី ឬ ប្រុស)\n"
        "4. ទទួលបានអត្ថបទបកប្រែ និងឯកសារសម្លេង Voice MP3 យ៉ាងរលូនភ្លាមៗ!"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

# ទទួលវីដេអូផ្ទាល់ពីអ្នកប្រើប្រាស់
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    video = message.video if message else None
    
    if not video:
        await message.reply_text("សូមផ្ញើមកជារូបភាពវីដេអូ (Video) មកកាន់ខ្ញុំ!")
        return

    video_file = await context.bot.get_file(video.file_id)
    file_path = f"downloaded_{video.file_id}.mp4"
    await video_file.download_to_drive(file_path)
    
    context.user_data['video_file_path'] = file_path

    keyboard = [
        [InlineKeyboardButton("🇰🇭 ភាសាខ្មែរ (Khmer)", callback_data="lang_km")],
        [InlineKeyboardButton("🇺🇸 ភាសាអង់គ្លេស (English)", callback_data="lang_en")],
        [InlineKeyboardButton("🇹🇭 ភាសាថៃ (Thai)", callback_data="lang_th")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("🌐 សូមជ្រើសរើសភាសាដែលចង់បកប្រែ៖", reply_markup=reply_markup)

# កត់ត្រាភាសា និងបង្ហាញប៊ូតុងរើសសំឡេង
async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    lang_choice = query.data.split("_")[1]
    if lang_choice == "km":
        context.user_data['lang_code'] = "km"
        context.user_data['selected_lang'] = "ភាសាខ្មែរ"
    elif lang_choice == "en":
        context.user_data['lang_code'] = "en"
        context.user_data['selected_lang'] = "English"
    elif lang_choice == "th":
        context.user_data['lang_code'] = "th"
        context.user_data['selected_lang'] = "ភាសាថៃ (Thai)"

    keyboard = [
        [InlineKeyboardButton("👩 សំឡេងស្រី (Female Voice)", callback_data="voice_female")],
        [InlineKeyboardButton("👨 សំឡេងប្រុស (Male Voice)", callback_data="voice_male")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text("🗣️ សូមជ្រើសរើសប្រភេទសំឡេង (Voice Type)៖", reply_markup=reply_markup)

# បកប្រែវីដេអូដោយស្វ័យប្រវត្តិ និងបង្កើតឯកសារសម្លេង MP3
async def select_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    voice_type = query.data.split("_")[1]
    voice_label = "សំឡេងស្រី" if voice_type == "female" else "សំឡេងប្រុស"
    
    lang_code = context.user_data.get('lang_code', 'km')
    selected_lang = context.user_data.get('selected_lang', 'ភាសាខ្មែរ')
    file_path = context.user_data.get('video_file_path')

    await query.message.edit_text("⏳ កំពុង Upload និងរង់ចាំ Gemini វិភាគវីដេអូ... រង់ចាំបន្តិចបង!")

    video_uploaded = None
    audio_path = None

    try:
        # ១. Upload វីដេអូទៅ Gemini
        with open(file_path, "rb") as f:
            video_uploaded = ai_client.files.upload(file=f)

        # ២. រង់ចាំរហូតដល់ Gemini Server ដំណើរការវីដេអូរួចរាល់ (ACTIVE)
        while video_uploaded.state.name == "PROCESSING":
            time.sleep(2)
            video_uploaded = ai_client.files.get(name=video_uploaded.name)

        if video_uploaded.state.name == "FAILED":
            raise Exception("Gemini video processing failed.")

        # ៣. ហៅបញ្ជាបកប្រែសាច់រឿងពីវីដេអូ
        prompt = f"Summarize and translate the core content and speech of this video into {selected_lang} in detail as a clear voiceover script."
        response = ai_client.models.generate_content(
            model='gemini-1.5-flash',
            contents=[video_uploaded, prompt]
        )
        translated_text = response.text

        # ៤. បង្កើតឯកសារសម្លេង gTTS
        audio_path = f"translation_{voice_type}.mp3"
        tts = gTTS(text=translated_text, lang=lang_code, slow=False)
        tts.save(audio_path)

        # ៥. ផ្ញើអត្ថបទបកប្រែ និងឯកសារសម្លេង (Voice MP3) ជូន Telegram User
        await query.message.reply_text(f"📝 **អត្ថបទបកប្រែជា ({selected_lang})៖**\n\n{translated_text}")
        
        with open(audio_path, 'rb') as audio_file:
            await query.message.reply_audio(
                audio=audio_file,
                title=f"Translation ({selected_lang} - {voice_label})",
                caption=f"🎙️ ឯកសារសម្លេង ({voice_label}) សម្រាប់យកទៅប្រើប្រាស់ជាមួយវីដេអូ!"
            )

    except Exception as e:
        logger.error(f"Error processing direct video translation: {e}")
        await query.message.reply_text("❌ មានបញ្ហាក្នុងការវិភាគវីដេអូជាមួយ Gemini សូមព្យាយាមផ្ញើវីដេអូថ្មីម្តងទៀត!")

    finally:
        # សម្អាត File ទាំងអស់ចេញពី Server
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
        if video_uploaded:
            try:
                ai_client.files.delete(name=video_uploaded.name)
            except:
                pass

def main():
    t = Thread(target=run_flask)
    t.start()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    application.add_handler(CallbackQueryHandler(select_language, pattern="^lang_"))
    application.add_handler(CallbackQueryHandler(select_voice, pattern="^voice_"))

    print("Bot is starting with Direct Video Processing support...")
    application.run_polling()

if __name__ == "__main__":
    main()
