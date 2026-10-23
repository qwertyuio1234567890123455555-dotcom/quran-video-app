import os
import json
import math
import random
import subprocess
import requests
import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg
import arabic_reshaper
from bidi.algorithm import get_display

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

CLIENT_ID = '655750280827-ucv3jdsh0c8t515gd3ennafgvtj00a1l.apps.googleusercontent.com'
CLIENT_SECRET = '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'
SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']
REDIRECT_URI = "https://quran-video-app-4nhpdndsvuas3yjbv4jhsj.streamlit.app"

RECITERS = [
    {"name": "الشيخ مشاري العفاسي", "folder": "Alafasy_128kbps"},
    {"name": "الشيخ عبد الرحمن السديس", "folder": "Abdurrahmaan_As-Sudais_192kbps"},
    {"name": "الشيخ ماهر المعيقلي", "folder": "MaherAlMuaiqly128kbps"},
    {"name": "الشيخ سعود الشريم", "folder": "Saood_ash-Shuraym_128kbps"},
    {"name": "الشيخ ناصر القطامي", "folder": "Nasser_Alqatami_128kbps"}
]

# ----------------- وظائف معالجة النصوص والصوتيات والڤيديو -----------------

def format_arabic_text(text):
    reshaped_text = arabic_reshaper.reshape(text)
    return get_display(reshaped_text)

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

def generate_animated_background(width, height, surah_name, ayahs_text_list, reciter_name, show_watermark, session_id):
    frame_dir = os.path.join(os.getcwd(), f"frames_{session_id}")
    os.makedirs(frame_dir, exist_ok=True)
    
    combined_ayahs_raw = " ".join(ayahs_text_list)
    title_text = format_arabic_text(f"{surah_name}")
    ayah_text = format_arabic_text(combined_ayahs_raw)
    reciter_text = format_arabic_text(reciter_name)
    footer_text = format_arabic_text("موقع السعد للقرآن الكريم")

    try:
        font_title = ImageFont.truetype("arial.ttf", int(height * 0.055))
        font_ayah = ImageFont.truetype("arial.ttf", int(height * 0.045))
        font_reciter = ImageFont.truetype("arial.ttf", int(height * 0.038))
    except:
        font_title = ImageFont.load_default()
        font_ayah = ImageFont.load_default()
        font_reciter = ImageFont.load_default()

    stars = [(random.randint(0, width), random.randint(0, height), random.randint(1, 3)) for _ in range(30)]

    for i in range(30):
        img = Image.new("RGB", (width, height), color="#050b14")
        draw = ImageDraw.Draw(img)
        
        for x, y, size in stars:
            brightness = int(120 + 135 * math.sin(i * 0.3 + x))
            draw.ellipse([x, y, x + size, y + size], fill=(brightness, brightness, 255))

        margin = int(width * 0.03)
        draw.rectangle([margin, margin, width - margin, height - margin], outline="#d4af37", width=4)

        cx, cy = width // 2, height // 2
        draw.text((cx, int(height * 0.22)), title_text, fill="#facc15", anchor="mm", font=font_title)
        draw.text((cx, cy), ayah_text, fill="#ffffff", anchor="mm", font=font_ayah)
        draw.text((cx, int(height * 0.78)), reciter_text, fill="#38bdf8", anchor="mm", font=font_reciter)

        if show_watermark:
            draw.text((cx, height - int(height * 0.08)), footer_text, fill="#94a3b8", anchor="mm", font=font_reciter)

        img.save(os.path.join(frame_dir, f"frame_{i:04d}.png"))

def generate_quran_video(surah, start_ayah, num_ayahs, is_short, duration, show_watermark, reciter_info, session_id):
    out_filename = f"output_{session_id}_{'short' if is_short else 'long'}.mp4"
    out_path = os.path.join(os.getcwd(), out_filename)
    audio_path = os.path.join(os.getcwd(), f"temp_audio_{session_id}.mp3")
    width, height = (1080, 1920) if is_short else (1920, 1080)

    try:
        surah_name, total_surah_ayahs = get_surah_info(surah)
        ayahs_text_list, audio_files = [], []
        actual_consumed = 0
        
        for k in range(num_ayahs):
            current_a = start_ayah + k
            if current_a > total_surah_ayahs:
                break
            txt = get_ayah_text(surah, current_a)
            if txt:
                ayahs_text_list.append(txt + f" ﴿{current_a}﴾ ")
            
            a_url = f"https://everyayah.com/data/{reciter_info['folder']}/{surah:03d}{current_a:03d}.mp3"
            part_path = os.path.join(os.getcwd(), f"part_{session_id}_{k}.mp3")
            r = requests.get(a_url, timeout=10)
            if r.status_code == 200:
                with open(part_path, 'wb') as f:
                    f.write(r.content)
                audio_files.append(part_path)
                actual_consumed += 1

        if not audio_files:
            return False, "فشل تحميل الصوتيات!", 0, None

        with open(audio_path, 'wb') as outfile:
            for fname in audio_files:
                with open(fname, 'rb') as infile:
                    outfile.write(infile.read())
                try: os.remove(fname)
                except: pass

        generate_animated_background(width, height, surah_name, ayahs_text_list, reciter_info["name"], show_watermark, session_id)

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        dur_seconds = int(duration) if is_short else int(duration) * 60

        cmd = [
            ffmpeg_exe, "-y", "-framerate", "10", "-loop", "1",
            "-i", os.path.join(os.getcwd(), f"frames_{session_id}", "frame_%04d.png"),
            "-stream_loop", "-1", "-i", audio_path,
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-t", str(dur_seconds), "-pix_fmt", "yuv420p", out_path
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return True, (surah_name, actual_consumed), 0, out_path
        return False, "فشل معالجة الفيديو", 0, None
    except Exception as e:
        return False, str(e), 0, None

def upload_single_video(creds, video_path, video_title, description):
    try:
        credentials = Credentials(**creds)
        youtube = build('youtube', 'v3', credentials=credentials)
        body = {
            'snippet': {'title': video_title, 'description': description, 'tags': ['Quran', 'القرآن الكريم'], 'categoryId': '22'},
            'status': {'privacyStatus': 'public'}
        }
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        request_upload = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
        response = None
        while response is None:
            _, response = request_upload.next_chunk()
        return True, response.get('id')
    except Exception as e:
        return False, str(e)

# ----------------- واجهة المستخدم بخواص الجلسات المنفصلة (Multi-User) -----------------

st.set_page_config(page_title="موقع السعد للقرآن الكريم", page_icon="📖", layout="centered")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    html, body, [class*="css"]  {
        direction: RTL;
        text-align: right;
        font-family: 'Cairo', sans-serif;
    }
    div[data-baseweb="select"] {
        direction: RTL;
    }
    .stButton>button {
        width: 100%;
        background-color: #10b981;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        padding: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("📖 موقع السعد للقرآن الكريم")
st.caption("منصة لكل زائر لتوليد ونشر فيديوهات القرآن الكريم تلقائياً على قناته")

st.markdown("---")

# تهيئة الجلسة الخاصة بالمستخدم الحالي فقط
if 'user_creds' not in st.session_state:
    st.session_state.user_creds = None

if 'surah' not in st.session_state:
    st.session_state.surah = 1
if 'ayah' not in st.session_state:
    st.session_state.ayah = 1
if 'reciter_index' not in st.session_state:
    st.session_state.reciter_index = 0

# قسم ربط القناة
st.header("🔗 ربط قناتك الشخصية (Google OAuth)")

if st.session_state.user_creds:
    st.success("✅ قناتك مرتبطة حالياً وجاهزة للنشر!")
    if st.button("❌ تسجيل الخروج من القناة"):
        st.session_state.user_creds = None
        st.experimental_rerun()
else:
    st.warning("⚠️ لم تقم بربط قناتك بعد. قم بالربط لتبدأ بنشر فيديوهاتك.")
    
    flow = Flow.from_client_config(
        {"web": {
            "client_id": CLIENT_ID, 
            "client_secret": CLIENT_SECRET, 
            "auth_uri": "https://accounts.google.com/o/oauth2/auth", 
            "token_uri": "https://oauth2.googleapis.com/token"
        }},
        scopes=SCOPES, redirect_uri=REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    
    st.markdown(f'<a href="{auth_url}" target="_blank" style="display:inline-block;padding:12px 24px;background:#2563eb;color:white;text-decoration:none;border-radius:8px;font-weight:bold;">اضغط هنا لتسجيل الدخول وربط قناتك بـ Google</a>', unsafe_allow_html=True)
    
    st.caption("ملاحظة: إذا ظهر لك تحذير من جوجل (Unverified app)، اضغط على خيارات متقدمة (Advanced) ثم اختيار الانتقال إلى التطبيق (Go to app).")

    auth_code = st.text_input("أدخل كود التحقق (Code) المنسوخ من جوجل هنا:")
    if st.button("تأكيد وحفظ الربط لقناتي"):
        try:
            flow.fetch_token(code=auth_code)
            credentials = flow.credentials
            st.session_state.user_creds = {
                'token': credentials.token, 'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri, 'client_id': credentials.client_id,
                'client_secret': credentials.client_secret, 'scopes': credentials.scopes
            }
            st.success("تم ربط قناتك بنجاح! يمكنك الآن بدء التوليد والنشر.")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"خطأ في الرمز أو انتهت صلاحيته: {e}")

st.markdown("---")

# قسم إعدادات الفيديو والنشر
st.header("⚙️ إعدادات وتوليد الفيديو")

v_type = st.selectbox("نوع الفيديو المراد نشره:", ["short", "long", "both"], format_func=lambda x: "فيديو قصير (Shorts) فقط" if x=="short" else ("فيديو طويل فقط" if x=="long" else "طويل وقصير معاً"))
l_dur = st.selectbox("مدة الفيديو الطويل (بالدقائق):", [10, 30, 60])
s_dur = st.selectbox("مدة الفيديو القصير (بالثواني):", [30, 50])

current_reciter_obj = RECITERS[st.session_state.reciter_index % len(RECITERS)]
st.info(f"القارئ الحالي لهذا التوليد: **{current_reciter_obj['name']}**")

st.markdown("---")

if st.button("⚡ توليد ونشر الفيديو على قناتي الآن"):
    if not st.session_state.user_creds:
        st.error("يرجى ربط قناتك أولاً قبل الضغط على التوليد والنشر!")
    else:
        st.info("جاري سحب الصوتيات وتوليد الفيديو ونشره على قناتك، يرجى الانتظار...")
        session_id = str(random.randint(1000, 9999))
        
        cur_surah = st.session_state.surah
        cur_ayah = st.session_state.ayah
        
        results_msg = []

        if v_type in ["short", "both"]:
            success_s, res_data_s, _, v_path_s = generate_quran_video(cur_surah, cur_ayah, 3, True, s_dur, True, current_reciter_obj, session_id)
            if success_s:
                surah_name, consumed_s = res_data_s
                ok, video_id = upload_single_video(st.session_state.user_creds, v_path_s, f"تلاوة خاشعة - {surah_name} #Shorts", f"تلاوة مباركة من {surah_name}")
                if ok:
                    results_msg.append(f"تم رفع Shorts بنجاح (رقم الفيديو: {video_id})")
                    cur_ayah += consumed_s

        if v_type in ["long", "both"]:
            success_l, res_data_l, _, v_path_l = generate_quran_video(cur_surah, cur_ayah, 8, False, l_dur, True, current_reciter_obj, session_id)
            if success_l:
                surah_name, consumed_l = res_data_l
                ok, video_id = upload_single_video(st.session_state.user_creds, v_path_l, f"تلاوة خاشعة سورة {surah_name}", f"تلاوة مباركة سورة {surah_name}")
                if ok:
                    results_msg.append(f"تم رفع الفيديو الطويل بنجاح (رقم الفيديو: {video_id})")
                    cur_ayah += consumed_l

        if results_msg:
            st.success(" 🎉 " + " | ".join(results_msg))
            st.session_state.ayah = cur_ayah
            st.session_state.reciter_index += 1
        else:
            st.error("حدث خطأ أثناء التوليد أو النشر. يرجى التأكد من الرمز وإعادة المحاولة.")
