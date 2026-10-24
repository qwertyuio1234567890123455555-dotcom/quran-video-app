FROM python:3.10-slim

# تثبيت FFmpeg وأدوات النظام الأساسية للمعالجة
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# نسخ وتثبيت مكتبات بايثون
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع إلى السيرفر
COPY . .

# فتح البورت المطلوب وتشغيل السيرفر
EXPOSE 5000
CMD ["python", "main.py"]
