import os
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
    return "Telegram Multi-Language Translator Bot is running successfully!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Command /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🌍 **ស្វាគមន៍មកកាន់ Multi-Language Translator & Voice Bot!**\n\n"
        "វិធីប្រើប្រាស់៖\n"
        "1. ផ្ញើអត្ថបទ (Text) ដែលចង់បកប្រែមកទីនេះ\n"
        "2. ជ្រើសរើសភាសា (ខ្មែរ, អង់គ្លេស, ឬ ថៃ)\n"
        "3. ជ្រើសរើសប្រភេទសំឡេង (ស្រី ឬ ប្រុស)\n"
        "4. ទទួលបានអត្ថបទបកប្រែ និងឯកសារសម្លេង (Voice MP3) ភ្លាមៗតែម្ដង!"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

# ទទួលវីដេអូ (ឆ្លើយតបណែនាំ)
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 បងបានផ្ញើវីដេអូមក! ដើម្បីជៀសវាងការគាំង Error សូមបង **Copy អត្ថបទ ឬសាច់រឿងក្នុងវីដេអូនោះ ផ្ញើមកកាន់ខ្ញុំ (Text)** វិញ បន្ទាប់មកខ្ញុំនឹងបកប្រែជាសំឡេង Voice MP3 ជូនភ្លាមៗយ៉ាងរលូនបង!"
    )

# ទទួលអត្ថបទពីអ្នកប្រើប្រាស់
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_text = message.text if message else None
    
    if not user_text:
        return

    context.user_data['input_text'] = user_text

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
    
    lang_choice = query.data.split("_")[1] # km, en, th
    
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

# បកប្រែអត្ថបទ និងបង្កើតឯកសារសម្លេង MP3
async def select_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    voice_type = query.data.split("_")[1]
    voice_label = "សំឡេងស្រី" if voice_type == "female" else "សំឡេងប្រុស"
    
    lang_code = context.user_data.get('lang_code', 'km')
    selected_lang = context.user_data.get('selected_lang', 'ភាសាខ្មែរ')
    input_text = context.user_data.get('input_text', '')

    await query.message.edit_text("⏳ កំពុងបកប្រែអត្ថបទ និងបង្កើតឯកសារសម្លេង... រង់ចាំបន្តិចបង!")

    audio_path = None

    try:
        # ១. ប្រើប្រាស់ Gemini 1.5 Flash ដើម្បីបកប្រែអត្ថបទ
        prompt = f"Translate the following text into {selected_lang} accurately and naturally for a voiceover script:\n\n{input_text}"
        response = ai_client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt
        )
        translated_text = response.text

        # ២. បង្កើតឯកសារសម្លេង gTTS (ការពារ Error ភាសាថៃ)
        audio_path = f"translation_{voice_type}.mp3"
        tts = gTTS(text=translated_text, lang=lang_code, slow=False)
        tts.save(audio_path)

        # ៣. ផ្ញើអត្ថបទបកប្រែ និងឯកសារសម្លេង (Voice MP3) ទៅ Telegram User
        await query.message.reply_text(f"📝 **អត្ថបទបកប្រែជា ({selected_lang})៖**\n\n{translated_text}")
        
        with open(audio_path, 'rb') as audio_file:
            await query.message.reply_audio(
                audio=audio_file,
                title=f"Translation ({selected_lang} - {voice_label})",
                caption=f"🎙️ ឯកសារសម្លេង ({voice_label}) សម្រាប់យកទៅប្រើប្រាស់!"
            )

    except Exception as e:
        logger.error(f"Error in translation/TTS for lang {lang_code}: {e}")
        await query.message.reply_text("❌ មានបញ្ហាក្នុងការបកប្រែ ឬបង្កើតសម្លេង (អាចបណ្តាលមកពីទម្រង់អត្ថបទភាសាថៃ) សូមព្យាយាមម្តងទៀត!")

    finally:
        # សម្អាត File ออกจาก Server
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)

def main():
    t = Thread(target=run_flask)
    t.start()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(select_language, pattern="^lang_"))
    application.add_handler(CallbackQueryHandler(select_voice, pattern="^voice_"))

    print("Bot is starting with Multi-Language Thai support...")
    application.run_polling()

if __name__ == "__main__":
    main()
