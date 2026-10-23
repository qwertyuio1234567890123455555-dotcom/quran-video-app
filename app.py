import os
import json
import threading
import time
import subprocess
import traceback
import math
import random
from datetime import datetime
import requests
from flask import Flask, redirect, url_for, session, request, jsonify
from flask_cors import CORS
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg
import arabic_reshaper
from bidi.algorithm import get_display

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.secret_key = 'quran_saad_super_secret_key'
CORS(app, supports_credentials=True)

CLIENT_ID = '655750280827-ucv3jdsh0c8t515gd3ennafgvtj00a1l.apps.googleusercontent.com'
CLIENT_SECRET = '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'
REDIRECT_URI = 'http://localhost:5000/oauth2callback'

SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']

STATE_FILE = 'state.json'
SETTINGS_FILE = 'settings.json'
TOKEN_FILE = 'token.json'

RECITERS = [
    {"name": "الشيخ مشاري العفاسي", "folder": "Alafasy_128kbps"},
    {"name": "الشيخ عبد الرحمن السديس", "folder": "Abdurrahmaan_As-Sudais_192kbps"},
    {"name": "الشيخ ماهر المعيقلي", "folder": "MaherAlMuaiqly128kbps"},
    {"name": "الشيخ سعود الشريم", "folder": "Saood_ash-Shuraym_128kbps"},
    {"name": "الشيخ ناصر القطامي", "folder": "Nasser_Alqatami_128kbps"}
]

def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default
    return default

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_saved_credentials():
    if os.path.exists(TOKEN_FILE):
        creds_data = load_json(TOKEN_FILE, None)
        if creds_data:
            return Credentials(**creds_data)
    return None

def format_arabic_text(text):
    reshaped_text = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped_text)
    return bidi_text

def get_surah_info(surah_num):
    try:
        url = f"https://api.alquran.cloud/v1/surah/{surah_num}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()['data']
            return data['name'], data['numberOfAyahs']
    except:
        pass
    return f"سورة {surah_num}", 7

def get_ayah_text(surah, ayah):
    try:
        url = f"https://api.alquran.cloud/v1/ayah/{surah}:{ayah}/editions/quran-uthmani"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return res.json()['data']['text']
    except:
        pass
    return ""

def generate_animated_background(width, height, surah_name, ayahs_text_list, reciter_name, show_watermark, prefix=""):
    frame_dir = f"frames_{prefix}"
    if os.path.exists(frame_dir):
        for file in os.listdir(frame_dir):
            if file.endswith(".png"):
                try:
                    os.remove(os.path.join(frame_dir, file))
                except:
                    pass
    else:
        os.makedirs(frame_dir, exist_ok=True)
    
    combined_ayahs_raw = " ".join(ayahs_text_list)
    title_text = format_arabic_text(f"{surah_name}")
    ayah_text = format_arabic_text(combined_ayahs_raw)
    reciter_text = format_arabic_text(reciter_name)
    footer_text = format_arabic_text("موقع السعد للقرآن الكريم")

    try:
        font_size_title = int(height * 0.055)
        font_size_ayah = int(height * 0.045)
        font_size_reciter = int(height * 0.038)
        
        font_title = ImageFont.truetype("arial.ttf", font_size_title)
        font_ayah = ImageFont.truetype("arial.ttf", font_size_ayah)
        font_reciter = ImageFont.truetype("arial.ttf", font_size_reciter)
    except:
        font_title = ImageFont.load_default()
        font_ayah = ImageFont.load_default()
        font_reciter = ImageFont.load_default()

    total_frames = 30
    stars = [(random.randint(0, width), random.randint(0, height), random.randint(1, 3)) for _ in range(30)]

    for i in range(total_frames):
        img = Image.new("RGB", (width, height), color="#050b14")
        draw = ImageDraw.Draw(img)

        for y_wave in range(0, height, 30):
            offset = int(math.sin(i * 0.2 + y_wave * 0.03) * 15)
            r = 5 + (y_wave % 10)
            g = 20 + ((y_wave * 2) % 40) + offset
            b = 40 + (y_wave % 30)
            draw.rectangle([0, y_wave, width, y_wave + 30], fill=(r, g, b))

        for x, y, size in stars:
            brightness = int(120 + 135 * math.sin(i * 0.3 + x))
            draw.ellipse([x, y, x + size, y + size], fill=(brightness, brightness, 255))

        margin = int(width * 0.03)
        draw.rectangle([margin, margin, width - margin, height - margin], outline="#d4af37", width=4)
        draw.rectangle([margin + 8, margin + 8, width - (margin + 8), height - (margin + 8)], outline="#38bdf8", width=1)

        cx = width // 2
        cy = height // 2

        draw.text((cx, int(height * 0.22)), title_text, fill="#facc15", anchor="mm", font=font_title)
        draw.text((cx, cy), ayah_text, fill="#ffffff", anchor="mm", font=font_ayah)
        draw.text((cx, int(height * 0.78)), reciter_text, fill="#38bdf8", anchor="mm", font=font_reciter)

        if show_watermark:
            draw.text((cx, height - int(height * 0.08)), footer_text, fill="#94a3b8", anchor="mm", font=font_reciter)

        frame_path = os.path.join(frame_dir, f"frame_{i:04d}.png")
        img.save(frame_path)

def generate_quran_video(surah, start_ayah, num_ayahs, is_short, duration, show_watermark, reciter_info, output_filename="output.mp4"):
    audio_path = f"temp_audio_{'short' if is_short else 'long'}.mp3"
    width, height = (1080, 1920) if is_short else (1920, 1080)
    prefix = "short" if is_short else "long"

    try:
        surah_name, total_surah_ayahs = get_surah_info(surah)
        
        ayahs_text_list = []
        audio_files = []
        actual_consumed = 0
        
        for k in range(num_ayahs):
            current_a = start_ayah + k
            if current_a > total_surah_ayahs:
                break
            
            txt = get_ayah_text(surah, current_a)
            if txt:
                ayahs_text_list.append(txt + f" ﴿{current_a}﴾ ")
            
            a_url = f"https://everyayah.com/data/{reciter_info['folder']}/{surah:03d}{current_a:03d}.mp3"
            part_path = f"part_{prefix}_{k}.mp3"
            try:
                r = requests.get(a_url, timeout=10)
                if r.status_code == 200:
                    with open(part_path, 'wb') as f:
                        f.write(r.content)
                    audio_files.append(part_path)
                    actual_consumed += 1
            except:
                pass

        if not audio_files:
            return False, "فشل تحميل ملفات الصوت للآيات!", 0

        with open(audio_path, 'wb') as outfile:
            for fname in audio_files:
                with open(fname, 'rb') as infile:
                    outfile.write(infile.read())
                try:
                    os.remove(fname)
                except:
                    pass

        generate_animated_background(width, height, surah_name, ayahs_text_list, reciter_info["name"], show_watermark, prefix=prefix)

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        dur_seconds = int(duration) if is_short else int(duration) * 60

        frame_pattern = os.path.join(f"frames_{prefix}", "frame_%04d.png")
        cmd = [
            ffmpeg_exe, "-y",
            "-framerate", "10",
            "-loop", "1",
            "-i", frame_pattern,
            "-stream_loop", "-1",
            "-i", audio_path,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", str(dur_seconds),
            "-pix_fmt", "yuv420p",
            output_filename
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            return False, "فشل دمج الفيديو بـ FFmpeg", 0
        
        if os.path.exists(output_filename) and os.path.getsize(output_filename) > 0:
            return True, (surah_name, actual_consumed), 0
        
        return False, "لم يتم إنتاج ملف الفيديو", 0
    except Exception as e:
        traceback.print_exc()
        return False, str(e), 0

def upload_single_video(video_path, video_title, description):
    credentials = get_saved_credentials()
    if not credentials:
        return False, "لا يوجد حساب يوتيوب مرتبط!"
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        body = {
            'snippet': {
                'title': video_title,
                'description': description,
                'tags': ['Quran', 'القرآن الكريم', 'تلاوات خاشعة', 'موقع السعد'],
                'categoryId': '22'
            },
            'status': {
                'privacyStatus': 'public'
            }
        }
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        request_upload = youtube.videos().insert(
            part='snippet,status',
            body=body,
            media_body=media
        )
        response = None
        while response is None:
            status, response = request_upload.next_chunk()
        return True, response.get('id')
    except Exception as e:
        traceback.print_exc()
        return False, str(e)

def publish_video_process(override_settings=None):
    try:
        credentials = get_saved_credentials()
        if not credentials:
            return False, "يرجى ربط قناة يوتيوب أولاً!"

        settings = override_settings if override_settings else load_json(SETTINGS_FILE, {
            "type": "short",
            "short_duration": 30,
            "long_duration": 10,
            "daily_count": 1,
            "schedule_time": "18:00",
            "watermark": True
        })
        
        state = load_json(STATE_FILE, {"surah": 1, "ayah": 1, "reciter_index": 0})
        current_surah = state.get("surah", 1)
        current_ayah = state.get("ayah", 1)
        reciter_index = state.get("reciter_index", 0)

        current_reciter = RECITERS[reciter_index % len(RECITERS)]
        pub_type = settings.get("type", "short")
        short_dur = int(settings.get("short_duration", 30))
        long_dur = int(settings.get("long_duration", 10))
        show_watermark = settings.get("watermark", True)
        daily_count = int(settings.get("daily_count", 1))

        results_msg = []

        for loop_idx in range(daily_count):
            _, total_surah_ayahs = get_surah_info(current_surah)
            if current_ayah > total_surah_ayahs:
                current_surah += 1
                current_ayah = 1

            if pub_type in ["short", "both"]:
                num_ayahs_s = 3
                success_s, res_data_s, _ = generate_quran_video(current_surah, current_ayah, num_ayahs_s, True, short_dur, show_watermark, current_reciter, "output_short.mp4")
                if success_s:
                    surah_name, consumed_s = res_data_s
                    title_s = f"تلاوة خاشعة - {surah_name} بصوت {current_reciter['name']} #Shorts #القرآن_الكريم"
                    desc_s = f"تلاوة هادئة ومباركة من الذكر الحكيم ({surah_name}) بصوت القارئ {current_reciter['name']}.\n\n#القرآن_الكريم #shorts #quran #تلاوات_خاشعة #موقع_السعد"
                    ok, res_id = upload_single_video("output_short.mp4", title_s, desc_s)
                    if ok:
                        results_msg.append(f"الفيديو القصير #{loop_idx+1}")
                        current_ayah += consumed_s
                    else:
                        return False, f"فشل رفع الشورتس: {res_id}"
                else:
                    return False, f"فشل توليد الفيديو القصير: {res_data_s}"

            if pub_type in ["long", "both"]:
                _, total_surah_ayahs = get_surah_info(current_surah)
                if current_ayah > total_surah_ayahs:
                    current_surah += 1
                    current_ayah = 1

                num_ayahs_l = 8
                success_l, res_data_l, _ = generate_quran_video(current_surah, current_ayah, num_ayahs_l, False, long_dur, show_watermark, current_reciter, "output_long.mp4")
                if success_l:
                    surah_name, consumed_l = res_data_l
                    title_l = f"تلاوة هادئة ومباركة - {surah_name} بصوت {current_reciter['name']}"
                    desc_l = f"تلاوة عطرة خاشعة من آيات الذكر الحكيم ({surah_name}) بصوت القارئ {current_reciter['name']}.\n\n#القرآن_الكريم #تلاوات #Quran #موقع_السعد"
                    ok, res_id = upload_single_video("output_long.mp4", title_l, desc_l)
                    if ok:
                        results_msg.append(f"الفيديو الطويل #{loop_idx+1}")
                        current_ayah += consumed_l
                    else:
                        return False, f"فشل رفع الفيديو الطويل: {res_id}"
                else:
                    return False, f"فشل توليد الفيديو الطويل: {res_data_l}"

        save_json(STATE_FILE, {"surah": current_surah, "ayah": current_ayah, "reciter_index": reciter_index + 1})

        if results_msg:
            return True, "تم بنجاح توليد ونشر: " + " - ".join(results_msg) + f" بصوت ({current_reciter['name']})!"
        else:
            return False, "حدث خطأ أثناء النشر!"
    except Exception as e:
        traceback.print_exc()
        return False, str(e)

def background_scheduler():
    last_published_minute = ""
    while True:
        try:
            settings = load_json(SETTINGS_FILE, None)
            if settings and settings.get("schedule_time"):
                now = datetime.now().strftime("%H:%M")
                if now == settings.get("schedule_time") and now != last_published_minute:
                    publish_video_process()
                    last_published_minute = now
        except:
            pass
        time.sleep(30)

scheduler_thread = threading.Thread(target=background_scheduler, daemon=True)
scheduler_thread.start()

@app.route('/')
def index():
    if os.path.exists('index.html'):
        with open('index.html', 'r', encoding='utf-8') as f:
            return f.read()
    return "ملف index.html غير موجود!"

@app.route('/auth/google')
def auth_google():
    client_config = {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI]
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true', prompt='consent')
    session['state'] = state
    session['code_verifier'] = flow.code_verifier
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    state = session.get('state')
    code_verifier = session.get('code_verifier')
    client_config = {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI]
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES, state=state, redirect_uri=REDIRECT_URI)
    if code_verifier:
        flow.code_verifier = code_verifier
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    creds_data = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    save_json(TOKEN_FILE, creds_data)
    return redirect('http://localhost:5000/')

@app.route('/api/user_info', methods=['GET'])
def user_info():
    credentials = get_saved_credentials()
    if not credentials:
        return jsonify({"connected": False})
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        response = youtube.channels().list(mine=True, part='snippet').execute()
        if response.get('items'):
            title = response['items'][0]['snippet']['title']
            return jsonify({"connected": True, "channel_title": title})
    except:
        pass
    return jsonify({"connected": False})

@app.route('/api/save_settings', methods=['POST'])
def save_settings_data():
    data = request.json or {}
    save_json(SETTINGS_FILE, data)
    return jsonify({"status": "success", "message": "تم حفظ الإعدادات بنجاح!"})

@app.route('/api/test_publish', methods=['POST'])
def test_publish():
    data = request.json or {}
    save_json(SETTINGS_FILE, data)
    success, msg = publish_video_process(override_settings=data)
    if success:
        return jsonify({"status": "success", "message": "تم الحفظ والتوليد والنشر الفوري بدقة بنجاح!"})
    else:
        return jsonify({"error": msg}), 400

if __name__ == '__main__':
    app.run(port=5000, debug=True)
