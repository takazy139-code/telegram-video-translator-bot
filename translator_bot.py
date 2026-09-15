import os
import logging
import subprocess
from google import genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from flask import Flask
from multiprocessing import Process

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
        "✂️ **របៀបប្រើប្រាស់៖**\n"
        "1️⃣ កំណត់នាទីដែលចង់កាត់ ឧទាហរណ៍៖ វាយ `/cut 5` (កាត់ម្តង ៥នាទី)\n"
        "2️⃣ ផ្ញើវីដេអូរបស់អ្នកមកទីនេះ (ក្រោម ១ម៉ោង)\n"
        "3️⃣ រើសភាសាដើម្បីបកប្រែ និងទទួលវីដេអូកាត់ជាកង់ៗ!"
    )

# --- /cut COMMAND ---
async def cut_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ សូមបញ្ជាក់នាទីដែលចង់កាត់! ឧទាហរណ៍៖ `/cut 5` (កាត់ម្តង ៥នាទី)")
        return
    
    try:
        minutes = int(context.args[0])
        context.user_data['cut_minutes'] = minutes
        await update.message.reply_text(f"✅ បានកំណត់ការកាត់វីដេអូក្នុងទំហំ **{minutes} នាទី/កង់** រួចរាល់!\n👇 ឥឡូវសូមផ្ញើវីដេអូមកទីនេះបាន។")
    except ValueError:
        await update.message.reply_text("⚠️ សូមវាយបញ្ចូលលេខនាទីជាតួលេខត្រឹមត្រូវ ឧទាហរណ៍៖ `/cut 5`")

# --- HANDLE VIDEO UPLOAD & CUTTING ---
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.video or message.document:
        status_msg = await message.reply_text("📥 កំពុងទាញយកវីដេអូរបស់អ្នក... សូមរង់ចាំបន្តិច។")
        
        file = await (message.video.get_file() if message.video else message.document.get_file())
        input_path = "downloads_input.mp4"
        os.makedirs("downloads", exist_ok=True)
        await file.download_to_drive(input_path)
        
        context.user_data['pending_file'] = input_path
        
        chunk_minutes = context.user_data.get('cut_minutes', 5)
        chunk_seconds = chunk_minutes * 60
        
        await status_msg.edit_text(f"✂️ កំពុងកាត់វីដេអូជាកង់ៗ (កង់ละ {chunk_minutes} នាទី)...")
        
        cmd_probe = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {input_path}"
        try:
            duration = float(subprocess.check_output(cmd_probe, shell=True).decode().strip())
        except Exception:
            duration = 600
            
        os.makedirs("chunks", exist_ok=True)
        start_time = 0
        part = 1
        chunk_files = []
        
        while start_time < duration:
            output_file = f"chunks/part_{part}.mp4"
            cmd = f"ffmpeg -y -ss {start_time} -i {input_path} -t {chunk_seconds} -c copy {output_file}"
            subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                chunk_files.append(output_file)
            start_time += chunk_seconds
            part += 1
            
        await status_msg.delete()
        
        await message.reply_text(f"✅ កាត់វីដេអូរួចរាល់បានចំនួន **{len(chunk_files)} កង់**! កំពុងផ្ញើជូន...")
        for idx, cf in enumerate(chunk_files, 1):
            with open(cf, 'rb') as vid:
                await message.reply_video(video=vid, caption=f"🎬 ភាគទី {idx} (កង់ละ {chunk_minutes} នាទី)")
            os.remove(cf)
            
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
        await message.reply_text("🌐 តើបងចង់ឱ្យខ្ញុំជួយបកប្រែខ្លឹមសារវីដេអូនេះទៅជាភាសាអ្វីដែរ?", reply_markup=reply_markup)
        
    else:
        await message.reply_text("⚠️ សូមផ្ញើឯកសារវីដេអូមកកាន់ Bot នេះ។")

# --- CALLBACK QUERY FOR TRANSLATION ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    lang_code = query.data.split("_")[1]
    lang_names = {"km": "ខ្មែរ (Khmer)", "en": "អង់គ្លេស (English)", "th": "ថៃ (Thai)", "zh": "ចិន (Chinese)"}
    selected_lang = lang_names.get(lang_code, "Khmer")
    
    await query.edit_message_text(text=f"⏳ កំពុងដំណើរការបកប្រែទៅជា **{selected_lang}** ដោយ Gemini AI...")
    
    file_path = context.user_data.get('pending_file')
    if file_path and os.path.exists(file_path):
        try:
            video_file = client.files.upload(file=file_path)
            prompt = f"Listen to the audio, transcribe, and translate the core content into fluent {selected_lang}. Provide a structured summary and AI caption with hashtags."
            
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=[video_file, prompt]
            )
            
            result_text = response.text
            if len(result_text) > 4000:
                result_text = result_text[:4000] + "..."
                
            await query.message.reply_text(f"✨ **លទ្ធផលបកប្រែ & AI Caption ({selected_lang})៖**\n\n{result_text}", parse_mode="Markdown")
            
            os.remove(file_path)
            client.files.delete(name=video_file.name)
        except Exception as e:
            await query.message.reply_text(f"❌ មានបញ្ហាក្នុងការបកប្រែ: {str(e)}")
    else:
        await query.message.reply_text("❌ រកមិនឃើញឯកសារវីដេអូទេ សូមផ្ញើមកម្ដងទៀត។")

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
