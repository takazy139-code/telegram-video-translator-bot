import os
import logging
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from google import genai
from gtts import gTTS
from moviepy.editor import VideoFileClip, AudioFileClip

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

# ផ្ដើមដំណើរការ Google GenAI Client
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Flask Server សម្រាប់រក្សា Render ឱ្យដំណើរការ 24/7
app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Video Dubbing Bot is running successfully!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Command /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🎬 **ស្វាគមន៍មកកាន់ Video Dubbing Bot!**\n\n"
        "វិធីប្រើប្រាស់៖\n"
        "1. ផ្ញើវីដេអូមកទីនេះ\n"
        "2. ជ្រើសរើសភាសា (ខ្មែរ ឬ អង់គ្លេស)\n"
        "3. ជ្រើសរើសប្រភេទសំឡេង (ស្រី ឬ ប្រុស)\n"
        "4. ទទួលបានវីដេអូចូលរួមសំឡេងបកប្រែថ្មីរួចជាស្រេច!"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

# ទទួលវីដេអូ
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    video = message.video if message else None
    
    if not video:
        await message.reply_text("សូមផ្ញើមកជារូបភាពវីដេអូ (Video) មកកាន់ខ្ញុំ!")
        return

    # ទាញយកវីដេអូទុកក្នុង Temporary
    video_file = await context.bot.get_file(video.file_id)
    file_path = f"downloaded_{video.file_id}.mp4"
    await video_file.download_to_drive(file_path)
    
    context.user_data['video_file_path'] = file_path

    # បង្ហាញប៊ូតុងជ្រើសរើសភាសា
    keyboard = [
        [InlineKeyboardButton("🇰🇭 ភាសាខ្មែរ (Khmer)", callback_data="lang_km")],
        [InlineKeyboardButton("🇺🇸 ភាសាអង់គ្លេស (English)", callback_data="lang_en")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("🌐 សូមជ្រើសរើសភាសាដែលចង់បកប្រែ៖", reply_markup=reply_markup)

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
    await query.message.edit_text("🗣️ សូមជ្រើសរើសប្រភេទសំឡេង (Voice Type)៖", reply_markup=reply_markup)

# បង្កើតການបកប្រែ បញ្ចូលសំឡេង និងផ្ញើវីដេអូថ្មីត្រឡប់ទៅវិញ
async def select_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    voice_type = query.data.split("_")[1]
    voice_label = "សំឡេងស្រី" if voice_type == "female" else "សំឡេងប្រុស"
    
    lang_code = context.user_data.get('lang_code', 'km')
    selected_lang = context.user_data.get('selected_lang', 'ភាសាខ្មែរ')
    file_path = context.user_data.get('video_file_path')

    await query.message.edit_text("⏳ កំពុងបកប្រែ និងបញ្ចូលសំឡេងថ្មីចូលក្នុងវីដេអូ... រង់ចាំបន្តិចបង!")

    video_uploaded = None
    audio_path = None
    output_video_path = None

    try:
        # ១. បង្ហោះវីដេអូទៅ Gemini ដើម្បីសង្ខេបនិងបកប្រែអត្ថបទ
        with open(file_path, "rb") as f:
            video_uploaded = ai_client.files.upload(file=f)

        prompt = f"Summarize and translate the core content of this video into {selected_lang} concisely so it can be read as a voiceover script."
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[video_uploaded, prompt]
        )
        result_text = response.text

        # ២. បង្កើតឯកសារសម្លេង gTTS
        audio_path = f"dubbing_{voice_type}.mp3"
        tts = gTTS(text=result_text, lang=lang_code, slow=False)
        tts.save(audio_path)

        # ៣. ប្រើ MoviePy ដើម្បីដកសំឡេងដើមចេញ និងបញ្ចូលសំឡេងបកប្រែថ្មី
        output_video_path = f"dubbed_output_{voice_type}.mp4"
        
        video_clip = VideoFileClip(file_path)
        audio_clip = AudioFileClip(audio_path)

        # កំណត់រយៈពេលវីដេអូឱ្យត្រូវ ឬប្រសិនសម្លេងវែងជាងវីដេអូ អាចទុកតាមសម្លេង ឬកាត់តាមវីដេអូ
        # ទីនេះយើងយកសំឡេងថ្មីមកដាក់ជំនួសសំឡេងដើម
        final_video = video_clip.set_audio(audio_clip)
        
        # Write វីដេអូថ្មីចេញមក
        final_video.write_videofile(
            output_video_path, 
            codec='libx264', 
            audio_codec='aac', 
            fps=video_clip.fps if video_clip.fps else 24,
            preset='ultrafast',
            logger=None
        )

        # បិទ Clips ទាំងអស់ដើម្បីលុប Cache
        video_clip.close()
        audio_clip.close()
        final_video.close()

        # ៤. ផ្ញើវីដេអូដែលបានបញ្ចូលសំឡេងរួចទៅ Telegram User
        await query.message.reply_text(f"✅ **ការបកប្រែសម្រេចជោគជ័យ ({selected_lang} - {voice_label})!**")
        
        with open(output_video_path, 'rb') as vid_file:
            await query.message.reply_video(
                video=vid_file,
                caption=f"🎬 វីដេអូបកប្រែជា {selected_lang} ({voice_label})"
            )

    except Exception as e:
        logger.error(f"Error in video dubbing: {e}")
        await query.message.reply_text("❌ មានបញ្ហាក្នុងការកែច្នៃវីដេអូ សូមព្យាយាមផ្ញើរវីដេអូថ្មីម្តងទៀត!")

    finally:
        # សម្អាត File ទាំងអស់ចេញពី Server ដើម្បីកុំឱ្យធ្ងន់ Disk
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
        if output_video_path and os.path.exists(output_video_path):
            os.remove(output_video_path)
        if video_uploaded:
            try:
                ai_client.files.delete(name=video_uploaded.name)
            except:
                pass

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

    print("Bot is starting with Video Dubbing support...")
    application.run_polling()

if __name__ == "__main__":
    main()
