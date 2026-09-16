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

# ផ្ទៀងផ្ទាត់ API Keys
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("សូមកំណត់ TELEGRAM_BOT_TOKEN ក្នុង Environment Variables!")
if not GEMINI_API_KEY:
    raise ValueError("សូមកំណត់ GEMINI_API_KEY ក្នុង Environment Variables!")

# ផ្ដើមដំណើរការ Google GenAI Client
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Flask Server សម្រាប់រក្សា Render ឱ្យដំណើរការ 24/7
app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Video Translator & Voice Bot is running successfully!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Command /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "ស្វាគមន៍! ខ្ញុំជា Video Cutter, Translator & Voice Bot\n\n"
        "វិធីប្រើប្រាស់៖\n"
        "1. ផ្ញើវីដេអូមកទីនេះ\n"
        "2. ជ្រើសរើសភាសា និងសំឡេង (ស្រី ឬ ប្រុស)\n"
        "3. ទទួលបានអត្ថបទបកប្រែ និងឯកសារសម្លេង (Voice MP3) យកទៅប្រើប្រាស់!"
    )
    await update.message.reply_text(welcome_text)

# ទទួលវីដេអូ ឬឯកសារ
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.callback_query.message
    video = update.message.video if update.message else None
    
    if not video:
        await message.reply_text("សូមផ្ញើមកជារូបភាពវីដេអូ (Video) មកកាន់ខ្ញុំ!")
        return

    # ទាញយកវីដេអូទុកក្នុង Temporary
    video_file = await context.bot.get_file(video.file_id)
    file_path = f"downloaded_{video.file_id}.mp4"
    await video_file.download_to_drive(file_path)
    
    # រក្សាទុក file_path ក្នុង context.user_data សម្រាប់ជំហានបន្ទាប់
    context.user_data['video_file_path'] = file_path

    # បង្ហាញប៊ូតុងជ្រើសរើសភាសា
    keyboard = [
        [InlineKeyboardButton("🇰🇭 ភាសាខ្មែរ (Khmer)", callback_data="lang_km")],
        [InlineKeyboardButton("🇺🇸 ភាសាអង់គ្លេស (English)", callback_data="lang_en")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("សូមជ្រើសរើសភាសាដែលចต้องการបកប្រែ៖", reply_markup=reply_markup)

# កត់ត្រាភាសា និងបង្ហាញប៊ូតុងរើសសំឡេង (ស្រី ឬ ប្រុស)
async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    lang_choice = query.data.split("_")[1]
    context.user_data['lang_code'] = "km" if lang_choice == "km" else "en"
    context.user_data['selected_lang'] = "ភាសាខ្មែរ" if lang_choice == "km" else "English"

    keyboard = [
        [InlineKeyboardButton("👩 សំឡេងស្រី (Female Voice)", callback_data="voice_female")],
        [InlineKeyboardButton("👨 សំឡេងប្រុស (Male Voice)", callback_data="voice_male")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text("សូមជ្រើសរើសប្រភេទសំឡេង (Voice Type)៖", reply_markup=reply_markup)

# បង្កើតការបកប្រែ និងសម្លេង (Voice MP3)
async def select_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    voice_type = query.data.split("_")[1]
    voice_label = "សំឡេងស្រី" if voice_type == "female" else "សំឡេងប្រុស"
    
    lang_code = context.user_data.get('lang_code', 'km')
    selected_lang = context.user_data.get('selected_lang', 'ភាសាខ្មែរ')
    file_path = context.user_data.get('video_file_path')

    await query.message.edit_text("⏳ កំពុងដំណើរការបកប្រែ និងបង្កើតសម្លេង Voice MP3 ជូនបង... រង់ចាំបន្តិច!")

    try:
        # បង្ហោះវីដេអូទៅ Gemini សម្រាប់ការបកប្រែ
        with open(file_path, "rb") as f:
            video_uploaded = ai_client.files.upload(file=f)

        prompt = f"Translate the core content of this video into {selected_lang} in detail as a clear summary script."
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[video_uploaded, prompt]
        )
        result_text = response.text

        # បង្កើតឯកសារសម្លេង (Voice MP3) ជាមួយ gTTS ស្តង់ដារ
        audio_path = f"dubbing_{voice_type}.mp3"
        tts = gTTS(text=result_text, lang=lang_code, slow=False)
        tts.save(audio_path)

        # ផ្ញើលទ្ធផលទៅ Telegram User
        await query.message.reply_text(f"📝 **លទ្ធផលបកប្រែ ({selected_lang})៖**\n\n{result_text}")
        
        with open(audio_path, 'rb') as audio_file:
            await query.message.reply_audio(
                audio=audio_file, 
                title=f"Voice Dubbing ({selected_lang} - {voice_label})", 
                caption=f"ឯកសារសម្លេង ({voice_label}) បកប្រែជា {selected_lang}"
            )

        # សម្អាត File ក្នុង Server
        os.remove(audio_path)
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        ai_client.files.delete(name=video_uploaded.name)

    except Exception as e:
        logger.error(f"Error processing video: {e}")
        await query.message.reply_text("❌ មានបញ្តហាក្នុងការច្នៃវីដេអូ សូមព្យាយាមម្តងទៀត!")

def main():
    # ចាប់ផ្តើម Flask Server ក្នុង Background Thread
    t = Thread(target=run_flask)
    t.start()

    # ចាប់ផ្តើម Telegram Bot Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    application.add_handler(CallbackQueryHandler(select_language, pattern="^lang_"))
    application.add_handler(CallbackQueryHandler(select_voice, pattern="^voice_"))

    print("Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
