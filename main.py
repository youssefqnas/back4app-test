from flask import Flask
import threading
# هنا بنستورد الدالة الرئيسية من ملفك القديم
# تأكد أنك غيرت اسم ملفك القديم ليكون module قابل للاستيراد أو انسخ الكود هنا
# سنفترض أن ملفك القديم اسمه integration_test.py وفيه دالة main_process
import integration_test 

app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is ready! Go to /run to start."

@app.route('/run')
def run_bot():
    # تشغيل البوت في الخلفية عشان المتصفح ميعلقش
    thread = threading.Thread(target=run_script_wrapper)
    thread.start()
    return "🚀 Bot started in background! Check your database in a few minutes."

def run_script_wrapper():
    print("--- Triggered via Web ---")
    # هنا بنشغل الكود بتاعك
    # لازم تعدل ملف integration_test.py وتخلي الكود اللي في الآخر داخل دالة اسمها run_all() مثلاً
    try:
        integration_test.run_all_logic() 
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)