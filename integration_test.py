import requests
import random
import string
import time
import os
from playwright.sync_api import sync_playwright, TimeoutError
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from clickhouse_driver import Client 
from clickhouse_driver.errors import ServerException
from pyvirtualdisplay import Display

# =================================================================
# === الجزء الأول: دوال البريد المؤقت ===
# =================================================================

def random_string(length=10):
    """توليد نص عشوائي."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def create_temp_email_account():
    """إنشاء حساب بريد مؤقت."""
    print("\n--- بدء عملية إنشاء البريد الإلكتروني المؤقت ---")
    try:
        domains_resp = requests.get("https://api.mail.tm/domains")
        if domains_resp.status_code == 200:
            available_domains = [d['domain'] for d in domains_resp.json()['hydra:member']]
        else:
            available_domains = ["addy.biz", "mail.gw", "cold.fun"]
    except requests.exceptions.RequestException:
        available_domains = ["addy.biz", "mail.gw", "cold.fun"]

    while True:
        username = random_string()
        domain = random.choice(available_domains)
        email = f"{username}@{domain}"
        password = random_string(10) + "aA*1" 

        print(f"🔄 جاري محاولة إنشاء البريد: {email}")
        try:
            create_resp = requests.post("https://api.mail.tm/accounts", json={"address": email, "password": password})

            if create_resp.status_code == 201:
                print("✅ تم إنشاء الحساب بنجاح!")
                token_resp = requests.post("https://api.mail.tm/token", json={"address": email, "password": password})
                token = token_resp.json()["token"]
                headers = {"Authorization": f"Bearer {token}"}
                return {"email": email, "password": password, "headers": headers}
            
            elif create_resp.status_code == 429:
                print("⚠️ طلبات كثيرة جدًا. سننتظر 30 ثانية...")
                time.sleep(30)
            else:
                time.sleep(3)
        
        except requests.exceptions.RequestException:
            time.sleep(10)

def wait_for_clickhouse_verification_link(headers, timeout=90):
    """انتظار رابط التحقق."""
    print("\n--- ⏳ في انتظار وصول رسالة التحقق... ---")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            messages_resp = requests.get("https://api.mail.tm/messages", headers=headers)
            messages = messages_resp.json().get("hydra:member", [])

            for msg in messages:
                if "clickhouse" in msg["from"]["address"] or "ClickHouse" in msg["from"]["name"]:
                    print("📬 تم استلام رسالة من ClickHouse!")
                    msg_id = msg["id"]
                    msg_detail_resp = requests.get(f"https://api.mail.tm/messages/{msg_id}", headers=headers)
                    html_content = msg_detail_resp.json().get("html", [None])[0]

                    if html_content:
                        soup = BeautifulSoup(html_content, 'lxml')
                        # البحث عن الزر أو الرابط
                        verify_link_tag = soup.find('a', class_='action_button')
                        if not verify_link_tag:
                             verify_link_tag = soup.find('a', string=lambda text: text and "Verify" in text)

                        if verify_link_tag and verify_link_tag.has_attr('href'):
                            return verify_link_tag['href']
            time.sleep(5)
        except Exception as e:
            print(f"خطأ في البريد: {e}")
            time.sleep(5)
    return None

# =================================================================
# === الجزء الثاني: دالة الأتمتة (Playwright) ===
# =================================================================

def run_signup_automation(account_details):
    print("\n--- بدء الأتمتة باستخدام Playwright ---")
    email_address = account_details["email"]
    password_to_use = account_details["password"]
    headers = account_details["headers"]

    with sync_playwright() as p:
        # هام: --no-sandbox ضروري لتشغيل كروم داخل Docker
        browser = p.chromium.launch(
            headless=False, 
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        page = browser.new_page()
        
        try:
            # 1. التسجيل
            print("--- المرحلة 1: التسجيل ---")
            page.goto("https://auth.clickhouse.cloud/u/signup/", timeout=60000)
            try:
                page.get_by_role("button", name="Accept all cookies").click(timeout=5000)
            except: pass
            
            # قد تختلف الواجهة، نحاول الطرق المعتادة
            page.wait_for_load_state("networkidle")
            
            # تعبئة الإيميل
            if page.locator("#email").is_visible():
                page.locator("#email").fill(email_address)
                page.locator("._button-signup-id").click()
            else:
                # حالة زر Register link
                page.get_by_role("link", name="Register").click()
                page.locator("#email").fill(email_address)
                page.locator("._button-signup-id").click()

            page.locator("#password").fill(password_to_use)
            # checkbox
            page.locator("input[type='checkbox']").first.check() 
            # submit
            page.locator("button[type='submit']").first.click()
            
            # 2. التحقق
            print("\n--- المرحلة 2: انتظار الرابط ---")
            verification_link = wait_for_clickhouse_verification_link(headers)
            if not verification_link: raise Exception("Verification Link Not Found")
            
            page.goto(verification_link)
            
            # 3. تسجيل الدخول (إذا طلب ذلك)
            try:
                if page.locator("#username").is_visible(timeout=10000):
                    page.locator("#username").fill(email_address)
                    page.locator("._button-login-id").click()
                    page.locator("#password").fill(password_to_use)
                    page.locator("._button-login-password").click()
            except:
                print("يبدو أنه تم تسجيل الدخول تلقائياً")

            # 4. بدء التجربة
            print("\n--- المرحلة 4: إنشاء الخدمة ---")
            # محاولة ضغط الأزرار المحتملة لبدء الخدمة
            try:
                start_btn = page.locator('[data-testid*="start-trial"]')
                start_btn.wait_for(timeout=30000)
                start_btn.click()
            except:
                print("لم يظهر زر Start Trial، ربما نحن بالداخل بالفعل.")

            # إعداد الخدمة
            page.locator('[data-testid="select-trigger"]').first.click()
            page.locator('[data-testid="cloud-provider-option-gcp"]').click()
            page.locator('[data-testid="select-trigger"]').nth(1).click()
            # اختيار ريجون عشوائي أو محدد (Singapore)
            page.get_by_text("Singapore").first.click()
            
            page.locator('[data-testid="create-service-button"]').click()
            
            # 5. استخراج البيانات
            print("\n--- المرحلة 5: الانتظار واستخراج البيانات ---")
            
            # تخطي الاستبيان
            try:
                page.locator('[data-testid="entry-questionnaire-skip-button"]').click(timeout=60000)
            except: pass
            
            # الذهاب للإعدادات لتغيير الباسورد
            page.locator('[data-testid="settingsSidebarButton"]').click()
            
            # انتظار تفعيل زر Reset
            print("⌛️ ننتظر تفعيل زر Reset Password...")
            reset_btn = page.locator('[data-testid="reset-pwd-btn"]:not([disabled])')
            reset_btn.wait_for(timeout=300000) # 5 دقائق انتظار كحد أقصى لانتهاء الـ Provisioning
            reset_btn.click()
            
            # الحصول على الباسورد الجديد
            time.sleep(2)
            page.locator('button[data-testid="password-display-eye-icon"]').click()
            new_ch_password = page.locator('p[data-testid="container"].fs-exclude').inner_text()
            
            # إغلاق النافذة
            page.locator('button:has(svg[aria-label="cross"])').click()
            time.sleep(1)

            # الذهاب للوحة المتقدمة لجلب الهوست
            try:
                page.locator('[data-testid="advancedDashboardSidebarButton"]').click(timeout=5000)
            except:
                page.locator('[data-testid="monitoringSidebarButton"]').click()
                page.locator('[data-testid="advancedDashboardSidebarButton"]').click()

            # جلب الرابط
            dashboard_link = page.get_by_role("link", name="native advanced dashboard")
            dashboard_link.wait_for()
            href = dashboard_link.get_attribute("href")
            parsed_url = urlparse(href)
            ch_host = parsed_url.netloc.split(':')[0]
            
            browser.close()
            return ch_host, new_ch_password

        except Exception as e:
            print(f"❌ خطأ في الأتمتة: {e}")
            try:
                page.screenshot(path="error.png")
            except: pass
            browser.close()
            return None, None

# =================================================================
# === الجزء الثالث: تخزين البيانات ===
# =================================================================

def store_credentials_in_clickhouse(data_to_store):
    print("\n--- 💾 تخزين البيانات ---")
    
    # إعدادات قاعدة البيانات الرئيسية (الثابتة)
    main_db_host = "l5bxi83or6.eu-central-1.aws.clickhouse.cloud"
    main_db_user = "default"
    main_db_password = "8aJlVz_A2L4On"

    try:
        client = Client(
            host=main_db_host,
            user=main_db_user,
            password=main_db_password,
            database='default',
            secure=True,
            port=9440
        )
        
        data_row = [{
            'CLICKHOUSE_MAIL': data_to_store["email"],
            'CLICKHOUSE_MAIL_PASS': data_to_store["email_pass"],
            'CLICKHOUSE_HOST': data_to_store["host"],
            'CLICKHOUSE_PASSWORD': data_to_store["password"],
            'status': 'new',
            'last_status_update': time.strftime('%Y-%m-%d %H:%M:%S')
        }]

        insert_query = "INSERT INTO default.CLICKHOUSE_TABLES (CLICKHOUSE_MAIL, CLICKHOUSE_MAIL_PASS, CLICKHOUSE_HOST, CLICKHOUSE_PASSWORD) VALUES"
        client.execute(insert_query, data_row, types_check=True)
        print("🎉 تم الحفظ بنجاح!")

    except Exception as e:
        print(f"❌ خطأ في التخزين: {e}")
    finally:
        if 'client' in locals(): client.disconnect()

# =================================================================
# === الجزء الرابع: الدالة المجمعة (التي ينادي عليها السيرفر) ===
# =================================================================

def run_all_logic():
    print("\n🚀 Starting Logic from Server...")
    
    # تشغيل الشاشة الوهمية لتغطية العملية بالكامل
    try:
        # حجم شاشة كبير لضمان ظهور العناصر
        with Display(visible=0, size=(1920, 1080)) as disp:
            print("🖥️ Virtual Display (Xvfb) Started.")
            
            account = create_temp_email_account()
            if account:
                host, pwd = run_signup_automation(account)
                if host and pwd:
                    final_data = {
                        "email": account["email"],
                        "email_pass": account["password"],
                        "host": host,
                        "password": pwd
                    }
                    store_credentials_in_clickhouse(final_data)
                else:
                    print("❌ Failed to get credentials.")
            else:
                print("❌ Failed to create email.")
                
    except Exception as e:
        print(f"🔥 Critical Error in Wrapper: {e}")

# نقطة الدخول للتجربة المحلية
if __name__ == "__main__":
    run_all_logic()
