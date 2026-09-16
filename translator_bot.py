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
    return "Telegram Multi-Part Video Translator Bot is running successfully!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Command /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🎬 **ស្វាគមន៍មកកាន់ Multi-Part Video Translator Bot!**\n\n"
        "វិធីប្រើប្រាស់៖\n"
        "1. ផ្ញើវីដេអូមកទីនេះ (ទោះបីជាវីដេអូវែង ក៏ Bot ចែកជាកំណាត់ៗស្វ័យប្រវត្តិ)\n"
        "2. ជ្រើសរើសភាសា (ខ្មែរ ឬ អង់គ្លេស)\n"
        "3. ជ្រើសរើសប្រភេទសំឡេង (ស្រី ឬ ប្រុស)\n"
        "4. ទទួលបានអត្ថបទ និងឯកសារសម្លេង (Voice MP3) បែងចែកជា Parts យ៉ាងស្អាត!"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

# ទទួលវីដេអូ
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
        [InlineKeyboardButton("🇺🇸 ភាសាអង់គ្លេស (English)", callback_data="lang_en")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("🌐 សូមជ្រើសរើសភាសាដែលចង់បកប្រែ៖", reply_markup=reply_markup)

# កត់ត្រាភាសា និងបង្ហាញប៊ូតុងរើសសំឡេង
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
    await query.message.edit_text("🗣️ សូមជ្រើសរើសប្រភេទសំឡេង (Voice Type)៖", reply_markup=reply_markup)

# បែងចែកសាច់រឿងជាកំណាត់ៗ និងបង្កើតສម្លេង MP3 ជូនតាម Part នីមួយៗ
async def select_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    voice_type = query.data.split("_")[1]
    voice_label = "សំឡេងស្រី" if voice_type == "female" else "សំឡេងប្រុស"
    
    lang_code = context.user_data.get('lang_code', 'km')
    selected_lang = context.user_data.get('selected_lang', 'ភាសាខ្មែរ')
    file_path = context.user_data.get('video_file_path')

    await query.message.edit_text("⏳ កំពុងវិភាគ និងបែងចែកវីដេអូជាកំណាត់ៗ (Parts) พร้อมបង្កើតសំឡេង... រង់ចាំបន្តិចបង!")

    video_uploaded = None
    audio_files = []

    try:
        # ១. Upload វីដេអូទៅ Gemini
        with open(file_path, "rb") as f:
            video_uploaded = ai_client.files.upload(file=f)

        # ឱ្យ Gemini បែងចែកជាផ្នែកៗ (Parts) យ៉ាងច្បាស់លាស់
        prompt = (
            f"Analyze this video and break down the translation and summary into 3 clear chronological parts "
            f"(Part 1, Part 2, Part 3) in {selected_lang}. "
            f"Format each part clearly starting with 'PART 1:', 'PART 2:', and 'PART 3:'."
        )
        
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[video_uploaded, prompt]
        )
        full_text = response.text

        # ផ្ញើអត្ថបទសរុបជូនបងជាមុនសិន
        await query.message.reply_text(f"📝 **អត្ថបទបកប្រែបែងចែកជាកំណាត់ៗ ({selected_lang})៖**\n\n{full_text}")

        # កាត់ចែកអត្ថបទតាម Part 1, Part 2, Part 3 ដើម្បីបង្កើតជា Voice MP3 ដាច់ដោយឡែកពីគ្នា
        parts = []
        if "PART 2" in full_text:
            # បើមានចែកជា Parts ស្រាប់
            raw_parts = full_text.split("PART ")
            for p in raw_parts:
                if p.strip():
                    parts.append("PART " + p.strip())
        else:
            # បើ Gemini មិនបានបែងចែក strict ទេ យើងចែកអត្ថបទជា ៣ កំណាត់ស្មើៗគ្នា
            chunk_size = len(full_text) // 3
            parts = [
                "Part 1: " + full_text[:chunk_size],
                "Part 2: " + full_text[chunk_size:chunk_size*2],
                "Part 3: " + full_text[chunk_size*2:]
            ]

        # ២. បង្កើតឯកសារសម្លេង Voice MP3 តាមកំណាត់នីមួយៗ
        for i, part_text in enumerate(parts[:3], start=1):
            audio_path = f"part_{i}_{voice_type}.mp3"
            tts = gTTS(text=part_text, lang=lang_code, slow=False)
            tts.save(audio_path)
            audio_files.append((audio_path, i))

        # ៣. ផ្ញើឯកសារសម្លេង MP3 ជូនតាម Part នីមួយៗទៅ Telegram User
        for audio_path, i in audio_files:
            with open(audio_path, 'rb') as audio_file:
                await query.message.reply_audio(
                    audio=audio_file,
                    title=f"Part {i} ({selected_lang} - {voice_label})",
                    caption=f"🎙️ ឯកសារសម្លេង Part {i} ({voice_label})"
                )

    except Exception as e:
        logger.error(f"Error in multi-part processing: {e}")
        await query.message.reply_text("❌ មានបញ្ហាកในการបកប្រែវីដេអូ សូមព្យាយាមផ្ញើរវីដេអូថ្មីម្តងទៀត!")

    finally:
        # សម្អាត File ទាំងអស់ចេញពី Server
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        for audio_path, _ in audio_files:
            if os.path.exists(audio_path):
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

    print("Bot is starting with Multi-Part Video Translation support...")
    application.run_polling()

if __name__ == "__main__":
    main()
