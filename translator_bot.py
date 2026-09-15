import os
import logging
import re
from google import genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from flask import Flask
from multiprocessing import Process
import subprocess

# --- FLASK WEB SERVER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Video Translator & Cutter Bot is running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- CONFIGURATIONS ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
    raise ValueError("❌ សូមកំណត់ TELEGRAM_BOT_TOKEN និង GEMINI_API_KEY ជាមុនសិន!")

client = genai.Client(api_key=GEMINI_API_KEY)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- /start COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 សួស្តី! ខ្ញុំជា Video Translation & Cutter Bot.\n\n"
        "✂️ **មុខងារពិសេសៗ៖**\n"
        "1️⃣ ផ្ញើវីដេអូរបស់អ្នកមក (ក្រោម ១ម៉ោង)\n"
        "2️⃣ កាត់វីដេអូជាកង់ៗ (Segments) តាមនាទីដែលចង់បាន ឧទាហរណ៍៖ `/cut 10` (កាត់ម្តង ១០នាទី)\n"
        "3️⃣ បកប្រែភាសា និងបង្កើត AI Caption + Hashtag ស្វ័យប្រវត្តិ!\n\n"
        "🌐 គ្រាន់តែ Upload វីដេអូចូលទីនេះដើម្បីចាប់ផ្តើម!"
    )

# --- HELPER: SPLIT VIDEO INTO CHUNKS USING FFMPEG ---
def split_video(input_file, chunk_duration_minutes=10):
    chunk_duration_seconds = chunk_duration_minutes * 60
    # រកមើលរយៈពេលសរុបរបស់វីដេអូ
    cmd_probe = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {input_file}"
    try:
        duration = float(subprocess.check_output(cmd_probe, shell=True).decode().strip())
    except Exception:
        duration = 600 # ស្មានទុក ១០នាទីបើពិនិត្យមិនកើត

    os.makedirs("chunks", exist_ok=True)
    chunk_files = []
    
    start_time = 0
    part = 1
    while start_time < duration:
        output_file = f"chunks/part_{part}.mp4"
        cmd = f"ffmpeg -y -ss {start_time} -i {input_file} -t {chunk_duration_seconds} -c copy {output_file}"
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            chunk_files.append(output_file)
        start_time += chunk_duration_seconds
        part += 1
        
    return chunk_files

# --- HANDLE VIDEO UPLOAD ---
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.video or message.document:
        file = await (message.video.get_file() if message.video else message.document.get_file())
        file_path = "downloads_input.mp4"
        os.makedirs("downloads", exist_ok=True)
        await file.download_to_drive(file_path)
        
        context.user_data['pending_file'] = file_path
        
        # បង្ហាញប៊ូតុងជ្រើសរើសភាសា
        keyboard = [
            [
                InlineKeyboardButton("🇰🇭 ខ្មែរ (Khmer)", callback_data="lang_km"),
                InlineKeyboardButton("🇺🇸 អង់គ្លេស (English)", callback_data="lang_en")
            ],
            [
                InlineKeyboardButton("🇹🇭 ថៃ (Thai)", callback_data="lang_th"),
                InlineKeyboardButton("🇨🇳 ចិន (Chinese)", callback_data="lang_zh")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text("✅ ទទួលបានវីដេអូជោគជ័យ!\n🌐 សូមជ្រើសរើសភាសាគោលដៅដែលអ្នកចង់បកប្រែ៖", reply_markup=reply_markup)
    else:
        await message.reply_text("⚠️ សូមផ្ញើឯកសារវីដេអូ (Video File) មកកាន់ Bot នេះ។")

# --- GENERATE AI CAPTION & HASHTAGS ---
def generate_ai_caption(text_summary: str) -> str:
    try:
        prompt = f"Based on this video content summary: '{text_summary}', write an engaging social media caption and 3 trending hashtags under 200 characters."
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
        )
        return response.text
    except Exception:
        return "📌 វីដេអូបកប្រែដោយ AI Bot\n#Translation #Video #Trending"

# --- CALLBACK QUERY (LANGUAGE SELECTION & TRANSLATION) ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    lang_code = query.data.split("_")[1]
    lang_names = {"km": "ខ្មែរ (Khmer)", "en": "អង់គ្លេស (English)", "th": "ថៃ (Thai)", "zh": "ចិន (Chinese)"}
    selected_lang = lang_names.get(lang_code, "Khmer")
    
    await query.edit_message_text(text=f"⏳ កំពុងដំណើរការវិភាគ និងបកប្រែទៅជា **{selected_lang}** ដោយ Gemini AI, សូមរង់ចាំបន្តិច...")
    
    file_path = context.user_data.get('pending_file')
    
    if file_path and os.path.exists(file_path):
        try:
            # Upload ទៅកាន់ Gemini AI
            video_file = client.files.upload(file=file_path)
            
            prompt = f"Listen to the audio, transcribe, and translate the core content into fluent {selected_lang}. Provide a structured summary of the video."
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=[video_file, prompt]
            )
            
            translation_result = response.text
            ai_caption = generate_ai_caption(translation_result[:300])
            
            final_message = f"✨ **លទ្ធផលបកប្រែ ({selected_lang})៖**\n\n{translation_result}\n\n📝 **AI Caption & Hashtag:**\n{ai_caption}"
            if len(final_message) > 4000:
                final_message = final_message[:4000] + "..."
                
            await query.message.reply_text(final_message, parse_mode="Markdown")
            
            # លុបไฟล์ដើមចោល
            os.remove(file_path)
            client.files.delete(name=video_file.name)
            
        except Exception as e:
            await query.message.reply_text(f"❌ មានបញ្ហាក្នុងការបកប្រែជាមួយ AI: {str(e)}")
    else:
        await query.message.reply_text("❌ រកមិនឃើញឯកសារវីដេអូទេ សូមផ្ញើមកម្ដងទៀត។")

# --- /cut COMMAND (OPTION TO SPLIT VIDEO INTO CHUNKS) ---
async def cut_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ សូមបញ្ជាក់នាទីដែលចង់កាត់! ឧទាហរណ៍៖ `/cut 5` (កាត់ម្តង ៥នាទី)")
        return
    
    try:
        minutes = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ សូមใส่លេខនាទីជាតួលេខត្រឹមត្រូវ ឧទាហរណ៍៖ `/cut 10`")
        return

    await update.message.reply_text(f"✂️ កំពុងត្រៀមកាត់វីដេអូជាកង់ៗ (ក្នុងទំហំ {minutes} នាទី/កង់)... សូមផ្ញើវីដេអូ ឬរង់ចាំបន្តិច។")

# --- MAIN FUNCTION ---
def main():
    p = Process(target=run_flask)
    p.start()

    app_bot = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("cut", cut_command))
    app_bot.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    app_bot.add_handler(CallbackQueryHandler(button_callback, pattern="^lang_"))

    print("🤖 Video Translator & Cutter Bot is running...")
    app_bot.run_polling()

if __name__ == '__main__':
    main()