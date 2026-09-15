import os
import logging
import subprocess
from google import genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from flask import Flask
from multiprocessing import Process
from gtts import gTTS
from pydub import AudioSegment

# --- FLASK WEB SERVER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Video Cutter, Translator & Voice Bot is running 24/7"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- CONFIGURATIONS ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
    raise ValueError("សូមកំណត់ TELEGRAM_BOT_TOKEN និង GEMINI_API_KEY ជាមុនសិន!")

client = genai.Client(api_key=GEMINI_API_KEY)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- /start COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "សួស្តី! ខ្ញុំជា Video Cutter, Translator & Voice Bot\n\n"
        "របៀបប្រើប្រាស់៖\n"
        "1. ផ្ញើវីដេអូរបស់អ្នកមកទីនេះ\n"
        "2. រើសទំហំនាទីដែលចង់កាត់\n"
        "3. រើសភាសា និងរើសប្រភេទសម្លេង (ស្រី ឬ ប្រុស)\n"
        "4. ទទួលបានទាំងអត្ថបទសង្ខេប និងឯកសារសម្លេង (Voice MP3) យកទៅប្រើប្រាស់!"
    )

# --- HANDLE VIDEO UPLOAD ---
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.video or message.document:
        status_msg = await message.reply_text("កំពុងទាញយកវីដេអូរបស់អ្នក សូមរង់ចាំបន្តិច...")
        
        file = await (message.video.get_file() if message.video else message.document.get_file())
        input_path = "downloads_input.mp4"
        os.makedirs("downloads", exist_ok=True)
        await file.download_to_drive(input_path)
        
        context.user_data['pending_file'] = input_path
        await status_msg.delete()
        
        keyboard = [
            [
                InlineKeyboardButton("⏱️ ៥ នាទី/កង់", callback_data="cut_5"),
                InlineKeyboardButton("⏱️ ១០ នាទី/កង់", callback_data="cut_10")
            ],
            [
                InlineKeyboardButton("⏱️ ១៥ នាទី/កង់", callback_data="cut_15"),
                InlineKeyboardButton("⏱️ ២០ នាទី/កង់", callback_data="cut_20")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text("តើបងចង់កាត់វីដេអូនេះក្នុងទំហំប៉ុន្មាននាទីក្នុងមួយកង់?", reply_markup=reply_markup)
    else:
        await message.reply_text("សូមផ្ញើឯកសារវីដេអូមកកាន់ Bot នេះ។")

# --- CALLBACK FOR CUTTING MINUTES ---
async def cut_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    minutes = int(query.data.split("_")[1])
    chunk_seconds = minutes * 60
    
    await query.edit_message_text(text=f"កំពុងកាត់វីដេអូជាកង់ៗ (កង់ละ {minutes} នាទី)... សូមរង់ចាំបន្តិច។")
    
    input_path = context.user_data.get('pending_file')
    if not input_path or not os.path.exists(input_path):
        await query.message.reply_text("រកមិនឃើញឯកសារវីដេអូទេ សូមផ្ញើមកម្ដងទៀត។")
        return
        
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
        
    await query.message.reply_text(f"កាត់វីដេអូរួចរាល់បានចំនួន {len(chunk_files)} កង់! កំពុងផ្ញើជូន...")
    
    for idx, cf in enumerate(chunk_files, 1):
        with open(cf, 'rb') as vid:
            await query.message.reply_video(video=vid, caption=f"ភាគទី {idx} (កង់ละ {minutes} នាទី)")
        os.remove(cf)
        
    # បន្ទាប់ពីកាត់រួច ឱ្យជ្រើសរើសភាសាជាមុនសិន
    keyboard = [
        [
            InlineKeyboardButton("ខ្មែរ (Khmer)", callback_data="lang_km"),
            InlineKeyboardButton("អង់គ្លេស (English)", callback_data="lang_en")
        ],
        [
            InlineKeyboardButton("ថៃ (Thai)", callback_data="lang_th"),
            InlineKeyboardButton("ចិន (Chinese)", callback_data="lang_zh")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("តើបងចង់បកប្រែជាភាសាអ្វីដែរ?", reply_markup=reply_markup)

# --- CALLBACK FOR LANGUAGE SELECTION ---
async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    lang_code = query.data.split("_")[1]
    context.user_data['selected_lang'] = lang_code
    
    # បន្ទាប់ពីរើសភាសា រួចសួររកប្រភេទសម្លេង (ស្រី ឬ ប្រុស)
    keyboard = [
        [
            InlineKeyboardButton("👩 សម្លេងស្រី (Female Voice)", callback_data="voice_female"),
            InlineKeyboardButton("👨 សម្លេងប្រុស (Male Voice)", callback_data="voice_male")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text="តើបងចង់បានប្រភេទសម្លេងអាន (Voice Dubbing) បែបណា?", reply_markup=reply_markup)

# --- CALLBACK FOR VOICE GENDER & FINAL PROCESSING ---
async def voice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    voice_type = query.data.split("_")[1] # female ឬ male
    lang_code = context.user_data.get('selected_lang', 'km')
    
    lang_names = {"km": "ខ្មែរ (Khmer)", "en": "អង់គ្លេស (English)", "th": "ថៃ (Thai)", "zh": "ចិន (Chinese)"}
    selected_lang = lang_names.get(lang_code, "Khmer")
    voice_label = "សម្លេងស្រី (Female)" if voice_type == "female" else "សម្លេងប្រុស (Male)"
    
    await query.edit_message_text(text=f"កំពុងដំណើរការបកប្រែជា {selected_lang} ({voice_label})... សូមរង់ចាំបន្តិច។")
    
    file_path = context.user_data.get('pending_file')
    if file_path and os.path.exists(file_path):
        try:
            video_file = client.files.upload(file=file_path)
            prompt = f"Listen to the audio, transcribe, and translate the core content into fluent {selected_lang}. Provide a single unified Title for the whole story, followed by a clear and structured summary. Do not include any hashtags."
            
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=[video_file, prompt]
            )
            
            result_text = response.text
            if len(result_text) > 4000:
                result_text = result_text[:4000] + "..."
                
            # ផ្ញើអត្ថបទចំណងជើង និងសេចក្តីសង្ខេប
            await query.message.reply_text(f"ចំណងជើងនិងសេចក្តីសង្ខេប ({selected_lang})៖\n\n{result_text}")
            
            # បង្កើតឯកសារសម្លេង (Voice MP3)
            raw_audio_path = "raw_output.mp3"
            final_audio_path = f"dubbing_{voice_type}.mp3"
            
            tts = gTTS(text=result_text, lang=lang_code, slow=False)
            tts.save(raw_audio_path)
            
            # ប្រសិនបើជ្រើសរើសសំឡេងប្រុស យើងកែ Pitch ឱ្យទាប និងក្រាស់ជាងមុន
            if voice_type == "male":
                sound = AudioSegment.from_mp3(raw_audio_path)
                # ផ្លាស់ប្តូរ Sample Rate ដើម្បីបញ្ចុះ Pitch ឱ្យទៅជាធ្ងន់បែបប្រុស
                new_sample_rate = int(sound.frame_rate * 0.82) # បន្ថយប្រហែល 18% ឱ្យសំឡេងធ្ងន់ក្រាស់
                male_sound = sound._spawn(sound.raw_data, overrides={'frame_rate': new_sample_rate})
                male_sound = male_sound.set_frame_rate(44100)
                male_sound.export(final_audio_path, format="mp3")
            else:
                # សំឡេងស្រីរក្សាទុកទម្រង់ដើម
                os.rename(raw_audio_path, final_audio_path)
                
            if os.path.exists(raw_audio_path):
                os.remove(raw_audio_path)
            
            with open(final_audio_path, 'rb') as audio_file:
                await query.message.reply_audio(
                    audio=audio_file, 
                    title=f"Voice Dubbing ({selected_lang} - {voice_label})", 
                    caption=f"ឯកសារសម្លេង ({voice_label}) បកប្រែជាភាសា {selected_lang}"
                )
            
            os.remove(final_audio_path)
            os.remove(file_path)
            client.files.delete(name=video_file.name)
        except Exception as e:
            await query.message.reply_text(f"មានបញ្ហាក្នុងการបង្កើតសម្លេង៖ {str(e)}")
    else:
        await query.message.reply_text("រកមិនឃើញឯកសារវីដេអូទេ សូមផ្ញើមកម្ដងទៀត។")

# --- MAIN FUNCTION ---
def main():
    p = Process(target=run_flask)
    p.start()

    app_bot = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    app_bot.add_handler(CallbackQueryHandler(cut_callback, pattern="^cut_"))
    app_bot.add_handler(CallbackQueryHandler(language_callback, pattern="^lang_"))
    app_bot.add_handler(CallbackQueryHandler(voice_callback, pattern="^voice_"))

    print("Video Cutter, Translator & Voice Bot is running...")
    app_bot.run_polling()

if __name__ == 'main__':
    main()
