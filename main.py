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
from flask import Flask, redirect, url_for, session, request, jsonify, render_template_string
from flask_cors import CORS
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
import imageio_ffmpeg

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.secret_key = 'quran_saad_multi_user_super_secret_key'
CORS(app, supports_credentials=True)

CLIENT_ID = '655750280827-ucv3jdsh0c8t515gd3ennafgvtj00a1l.apps.googleusercontent.com'
CLIENT_SECRET = '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'

MULTI_USER_FILE = 'multi_user_data.json'

# --- إدارة بيانات الحسابات المتعددة ---
def load_all_users_data():
    if os.path.exists(MULTI_USER_FILE):
        try:
            with open(MULTI_USER_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_all_users_data(data):
    with open(MULTI_USER_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_user_data(channel_id):
    all_data = load_all_users_data()
    return all_data.get(channel_id, {})

def save_user_data(channel_id, user_dict):
    all_data = load_all_users_data()
    all_data[channel_id] = user_dict
    save_all_users_data(all_data)

def get_saved_credentials(channel_id):
    u_data = get_user_data(channel_id)
    creds_data = u_data.get('token')
    if creds_data:
        return Credentials(**creds_data)
    return None

# --- معالجة الملفات الصوتية المحلية واستخراج البيانات ---
def get_random_local_audio():
    valid_exts = ('.mp3', '.webm', '.m4a')
    audio_files = [f for f in os.listdir('.') if f.lower().endswith(valid_exts)]
    
    if not audio_files and os.path.exists('audio'):
        audio_files = [os.path.join('audio', f) for f in os.listdir('audio') if f.lower().endswith(valid_exts)]
        
    if not audio_files:
        return None, None
    
    selected_file = random.choice(audio_files)
    basename = os.path.basename(selected_file)
    clean_name = os.path.splitext(basename)[0].replace('_', ' ')
    
    metadata = {
        "title": f"تلاوة خاشعة | {clean_name}",
        "description": f"استمع إلى تلاوة خاشعة مباركة ({clean_name}).\n\nلا تنسى الاشتراك في القناة وتفعيل زر الجرس ليصلك كل جديد.\n\n#القرآن_الكريم #تلاوة_خاشعة #shorts",
        "tags": ["القرآن_الكريم", "تلاوات_خاشعة", "shorts", clean_name.replace(' ', '_')],
        "raw_name": clean_name
    }
    return selected_file, metadata

# --- توليد الفيديو بواسطة FFmpeg مع الخلفية ---
def generate_quran_video_local(audio_path, metadata, is_short, duration, output_filename="output.mp4"):
    width, height = (1080, 1920) if is_short else (1920, 1080)
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    dur_seconds = int(duration) if is_short else int(duration) * 60

    if os.path.exists('background.jpg'):
        bg_args = ['-loop', '1', '-i', 'background.jpg']
    else:
        bg_args = ['-f', 'lavfi', '-i', f'color=c=black:s={width}x{height}:r=25']

    cmd = [
        ffmpeg_exe, '-y',
        *bg_args,
        '-i', audio_path,
        '-c:v', 'libx264',
        '-tune', 'stillimage',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-pix_fmt', 'yuv420p',
        '-shortest',
        '-t', str(dur_seconds),
        output_filename
    ]

    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0 and os.path.exists(output_filename):
            return True, output_filename
        return False, "فشل دمج الفيديو بواسطة FFmpeg"
    except Exception as e:
        return False, str(e)

# --- رفع الفيديو إلى يوتيوب ---
def upload_video_for_channel(channel_id, video_path, video_title, description, tags):
    credentials = get_saved_credentials(channel_id)
    if not credentials:
        return False, "لا توجد صلاحية للرفع لهذا الحساب!"
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        body = {
            'snippet': {
                'title': video_title,
                'description': description,
                'tags': tags,
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

# --- عملية النشر الكاملة لحساب معين ---
def process_publish_for_channel(channel_id, override_settings=None):
    u_data = get_user_data(channel_id)
    if not u_data.get('token'):
        return False, "الحساب غير متصل بـ YouTube"

    settings = override_settings if override_settings else u_data.get('settings', {
        "type": "short",
        "short_duration": 30,
        "long_duration": 10,
        "daily_count": 1,
        "schedule_time": "18:00"
    })

    audio_path, meta = get_random_local_audio()
    if not audio_path:
        return False, "لم يتم العثور على أي ملفات صوتية محلياً!"

    pub_type = settings.get("type", "short")
    short_dur = int(settings.get("short_duration", 30))
    long_dur = int(settings.get("long_duration", 10))
    daily_count = int(settings.get("daily_count", 1))

    results = []

    for idx in range(daily_count):
        if pub_type in ["short", "both"]:
            out_file = f"output_short_{channel_id}.mp4"
            ok, res = generate_quran_video_local(audio_path, meta, True, short_dur, out_file)
            if ok:
                up_ok, video_id = upload_video_for_channel(channel_id, out_file, meta['title'], meta['description'], meta['tags'])
                if os.path.exists(out_file):
                    os.remove(out_file) # تنظيف تلقائي للمساحة
                if up_ok:
                    results.append(f"Shorts #{idx+1} (ID: {video_id})")
                else:
                    return False, f"فشل رفع فيديو الشورتس: {video_id}"

        if pub_type in ["long", "both"]:
            out_file = f"output_long_{channel_id}.mp4"
            ok, res = generate_quran_video_local(audio_path, meta, False, long_dur, out_file)
            if ok:
                up_ok, video_id = upload_video_for_channel(channel_id, out_file, meta['title'], meta['description'], meta['tags'])
                if os.path.exists(out_file):
                    os.remove(out_file) # تنظيف تلقائي للمساحة
                if up_ok:
                    results.append(f"الفيديو الطويل #{idx+1} (ID: {video_id})")
                else:
                    return False, f"فشل رفع الفيديو الطويل: {video_id}"

    return True, "تم بنجاح نشر: " + " - ".join(results)

# --- المجدل التلقائي لكافة الحسابات ---
def background_scheduler():
    last_published_minute = ""
    while True:
        try:
            now = datetime.now().strftime("%H:%M")
            if now != last_published_minute:
                all_users = load_all_users_data()
                for c_id, u_data in all_users.items():
                    user_settings = u_data.get('settings', {})
                    if user_settings.get('schedule_time') == now:
                        process_publish_for_channel(c_id)
                last_published_minute = now
        except Exception:
            pass
        time.sleep(30)

threading.Thread(target=background_scheduler, daemon=True).start()

# --- الواجهة الخاصة بـ Flask مع دعم تعدد الحسابات ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>موقع السعد - لوحة التحكم متعددة الحسابات</title>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">
    <style>
        :root { --bg: #07130c; --card: #0f2619; --primary: #10b981; --accent: #f59e0b; --text: #f3f4f6; }
        body { font-family: 'Cairo', sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 20px; display: flex; justify-content: center; }
        .wrapper { width: 100%; max-width: 800px; background: var(--card); border-radius: 20px; padding: 30px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        h1 { color: var(--accent); text-align: center; margin-top: 0; }
        .card { background: rgba(16,185,129,0.1); border: 1px solid var(--primary); padding: 15px; border-radius: 12px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
        select, input, button { width: 100%; padding: 12px; margin-top: 8px; border-radius: 10px; border: 1px solid #1e3a29; background: #07130c; color: white; font-family: 'Cairo'; }
        button { cursor: pointer; font-weight: bold; }
        .btn-auth { background: #2563eb; border: none; width: auto; padding: 10px 20px; }
        .btn-pub { background: var(--accent); color: black; border: none; margin-top: 15px; }
        #response-box { margin-top: 20px; padding: 15px; border-radius: 10px; display: none; text-align: center; }
    </style>
</head>
<body>
<div class="wrapper">
    <h1>🕌 لوحة تحكم نشر القرآن الكريم تلقائياً</h1>
    <div class="card">
        <div>
            <div>القناة الحالية:</div>
            <strong id="channelStatus">جاري الفحص...</strong>
        </div>
        <button class="btn-auth" onclick="window.location.href='/auth/google'">🔑 ربط قناة جديدة / تغيير</button>
    </div>

    <div>
        <label>🎬 نوع النشر:</label>
        <select id="videoType">
            <option value="short">فيديو قصير فقط (Shorts)</option>
            <option value="long">فيديو طويل فقط</option>
            <option value="both">قصير + طويل معاً</option>
        </select>

        <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px;">
            <div>
                <label>⏱️ مدة القصير (ثواني):</label>
                <input type="number" id="shortDuration" value="30">
            </div>
            <div>
                <label>⏱️ مدة الطويل (دقائق):</label>
                <input type="number" id="longDuration" value="10">
            </div>
        </div>

        <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px;">
            <div>
                <label>📅 مرات النشر يومياً:</label>
                <input type="number" id="dailyCount" value="1">
            </div>
            <div>
                <label>⏰ موعد النشر التلقائي:</label>
                <input type="time" id="scheduleTime" value="18:00">
            </div>
        </div>

        <button class="btn-pub" onclick="saveAndPublish()">🚀 حفظ الإعدادات والنشر الآن</button>
    </div>

    <div id="response-box"></div>
</div>

<script>
    window.onload = async function() {
        const res = await fetch("/api/user_info");
        const data = await res.json();
        if(data.connected) {
            document.getElementById("channelStatus").innerText = "✅ " + data.channel_title;
        } else {
            document.getElementById("channelStatus").innerText = "⚠️ غير متصل بقناة";
        }
    };

    async function saveAndPublish() {
        const msgBox = document.getElementById("response-box");
        msgBox.style.display = "block";
        msgBox.style.background = "rgba(59,130,246,0.2)";
        msgBox.innerText = "⏳ جاري التوليد والنشر على يوتيوب...";

        const payload = {
            type: document.getElementById("videoType").value,
            short_duration: document.getElementById("shortDuration").value,
            long_duration: document.getElementById("longDuration").value,
            daily_count: document.getElementById("dailyCount").value,
            schedule_time: document.getElementById("scheduleTime").value
        };

        const res = await fetch("/api/test_publish", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if(res.ok) {
            msgBox.style.background = "rgba(16,185,129,0.2)";
            msgBox.innerText = "🎉 " + data.message;
        } else {
            msgBox.style.background = "rgba(239,68,68,0.2)";
            msgBox.innerText = "❌ " + data.error;
        }
    }
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/auth/google')
def auth_google():
    redirect_uri = url_for('oauth2callback', _external=True)
    client_config = {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri]
        }
    }
    flow = Flow.from_client_config(client_config, scopes=['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly'], redirect_uri=redirect_uri)
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true', prompt='consent')
    session['state'] = state
    session['code_verifier'] = flow.code_verifier
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    state = session.get('state')
    code_verifier = session.get('code_verifier')
    redirect_uri = url_for('oauth2callback', _external=True)
    client_config = {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri]
        }
    }
    flow = Flow.from_client_config(client_config, scopes=['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly'], state=state, redirect_uri=redirect_uri)
    if code_verifier:
        flow.code_verifier = code_verifier
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials

    # معرفة الـ channel_id الخاص بالحساب للحفظ بشكل متعدد الحسابات
    youtube = build('youtube', 'v3', credentials=credentials)
    ch_res = youtube.channels().list(mine=True, part='id,snippet').execute()
    
    if ch_res.get('items'):
        channel_id = ch_res['items'][0]['id']
        channel_title = ch_res['items'][0]['snippet']['title']
        session['active_channel_id'] = channel_id

        u_data = get_user_data(channel_id)
        u_data['title'] = channel_title
        u_data['token'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        save_user_data(channel_id, u_data)

    return redirect('/')

@app.route('/api/user_info', methods=['GET'])
def user_info():
    c_id = session.get('active_channel_id')
    if not c_id:
        # أخذ أول قناة موجودة كافتراضية
        all_u = load_all_users_data()
        if all_u:
            c_id = list(all_u.keys())[0]
            session['active_channel_id'] = c_id

    if c_id:
        u_data = get_user_data(c_id)
        if u_data.get('token'):
            return jsonify({"connected": True, "channel_title": u_data.get('title', 'قناة يوتيوب')})
    return jsonify({"connected": False})

@app.route('/api/test_publish', methods=['POST'])
def test_publish():
    c_id = session.get('active_channel_id')
    if not c_id:
        return jsonify({"error": "يرجى تسجيل الدخول وربط قناة أولاً!"}), 400

    data = request.json or {}
    u_data = get_user_data(c_id)
    u_data['settings'] = data
    save_user_data(c_id, u_data)

    success, msg = process_publish_for_channel(c_id, override_settings=data)
    if success:
        return jsonify({"status": "success", "message": msg})
    else:
        return jsonify({"error": msg}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
