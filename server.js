const express = require('express');
const cors = require('cors');
const ffmpeg = require('fluent-ffmpeg');
const path = require('path');
const fs = require('fs');
const axios = require('axios');
const { google } = require('googleapis');

const app = express();
app.use(cors());
app.use(express.json());

// 🔑 مفاتيح Google OAuth المحدثة بعلامات التنصيص الصحيحة
const CLIENT_ID = '609917936834-idid3nrv45clmqo43urplt6a3lh4q7an.apps.googleusercontent.com';
const CLIENT_SECRET = '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';
const REDIRECT_URI = 'http://localhost:3000/oauth2callback';

const oauth2Client = new google.auth.OAuth2(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI);

// مجلد حفظ الفيديوهات المولدّة
const outputDir = path.join(__dirname, 'output');
if (!fs.existsSync(outputDir)){
    fs.mkdirSync(outputDir);
}

// 1️⃣ مسار بدء تسجيل الدخول وربط قناة اليوتيوب
app.get('/auth/google', (req, res) => {
    const scopes = [
        'https://www.googleapis.com/auth/youtube.upload',
        'https://www.googleapis.com/auth/youtube.readonly'
    ];

    const url = oauth2Client.generateAuthUrl({
        access_type: 'offline',
        scope: scopes
    });

    res.redirect(url);
});

// 2️⃣ مسار استقبال الـ Token بعد موافقة المستخدم
app.get('/oauth2callback', async (req, res) => {
    const code = req.query.code;
    try {
        const { tokens } = await oauth2Client.getToken(code);
        oauth2Client.setCredentials(tokens);
        res.send('<h1>✅ تم ربط قناة اليوتيوب بنجاح! يمكنك إغلاق هذه الصفحة والعودة للموقع.</h1>');
    } catch (error) {
        console.error('خطأ أثناء المصادقة:', error);
        res.status(500).send('فشل المصادقة مع يوتيوب');
    }
});

// 3️⃣ مسار توليد الفيديو عبر FFmpeg
app.post('/api/generate-video', async (req, res) => {
    try {
        const { audioUrl, ayahText } = req.body;
        if (!audioUrl || !ayahText) {
            return res.status(400).json({ error: 'البيانات غير مكتملة' });
        }

        const audioPath = path.join(outputDir, `audio_${Date.now()}.mp3`);
        const videoOutputPath = path.join(outputDir, `video_${Date.now()}.mp4`);
        
        const audioResponse = await axios({
            method: 'GET',
            url: audioUrl,
            responseType: 'stream'
        });

        const audioWriter = fs.createWriteStream(audioPath);
        audioResponse.data.pipe(audioWriter);

        audioWriter.on('finish', () => {
            ffmpeg()
                .input('color=c=121824:s=720x1280:r=30')
                .inputFormat('lavfi')
                .input(audioPath)
                .outputOptions([
                    '-c:v libx264',
                    '-tune stillimage',
                    '-c:a aac',
                    '-b:a 192k',
                    '-pix_fmt yuv420p',
                    '-shortest'
                ])
                .save(videoOutputPath)
                .on('end', () => {
                    res.json({
                        success: true,
                        message: 'تم توليد الفيديو بنجاح',
                        videoUrl: `/output/${path.basename(videoOutputPath)}`
                    });
                    if (fs.existsSync(audioPath)) fs.unlinkSync(audioPath);
                })
                .on('error', (err) => {
                    console.error('❌ خطأ في FFmpeg:', err);
                    res.status(500).json({ error: 'فشل توليد الفيديو' });
                    if (fs.existsSync(audioPath)) fs.unlinkSync(audioPath);
                });
        });
    } catch (error) {
        console.error('❌ خطأ عام:', error);
        res.status(500).json({ error: 'حدث خطأ داخلي في السيرفر' });
    }
});

app.use('/output', express.static(outputDir));

const PORT = 3000;
app.listen(PORT, () => {
    console.log(`🚀 السيرفر يعمل الآن وجاهز على البورت ${PORT}`);
});