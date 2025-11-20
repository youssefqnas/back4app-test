# استخدام نسخة بايثون خفيفة
FROM python:3.10-slim

# تثبيت أدوات النظام الضرورية للشاشة الوهمية والمتصفح
RUN apt-get update && apt-get install -y \
    xvfb \
    libgbm-dev \
    libnss3 \
    libasound2 \
    libxss1 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# إعداد مجلد العمل
WORKDIR /app

# نسخ الملفات
COPY requirements.txt .
COPY integration_test.py .
COPY main.py . 

# تثبيت المكتبات
RUN pip install --no-cache-dir -r requirements.txt

# تثبيت متصفحات Playwright
RUN playwright install chromium
RUN playwright install-deps

# أمر التشغيل (هنا هنشغل السيرفر الوهمي)
CMD ["gunicorn", "-b", "0.0.0.0:8080", "main:app", "--timeout", "300"]