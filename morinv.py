# -*- coding: utf-8 -*-
import requests
import time
import re
import os
import urllib3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# השתקת אזהרות SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= הגדרות =================
MORLEVI_USER = os.environ.get("MORLEVI_USER")
MORLEVI_PASS = os.environ.get("MORLEVI_PASS")
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")

SHOPIFY_STORE_URL = "360-pro.myshopify.com"
START_URL = "https://www.morlevi.co.il/AllProductsPrices/17,82,6,169,7,95,64,1,4,156,8,308,368,436,106,110,115,135,271,362?percent="
HOME_URL = "https://www.morlevi.co.il"

# הגדרות סינון קריטיות
VENDOR_NAME = "Morlevi"  # חייב להיות זהה לשם הספק בשופיפיי
TARGET_TAG = "MOR"       # חייב להיות זהה לתגית בשופיפיי
# ==========================================

def init_driver():
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--headless") 
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-blink-features=AutomationControlled")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def clean_ui(driver):
    try:
        driver.execute_script("""
            document.querySelectorAll('#site-popup-modal, .modal-backdrop, .access-wrapper, .gdpr-module').forEach(e => e.remove());
            document.querySelectorAll('[id*="chat"], [class*="chat"]').forEach(e => e.remove());
        """)
    except: pass

def login_to_morlevi(driver):
    print("🔑 מתחבר לאתר הספק...")
    driver.get(HOME_URL)
    time.sleep(3)
    clean_ui(driver)
    
    try:
        try: driver.find_element(By.PARTIAL_LINK_TEXT, "התחבר").click()
        except: driver.execute_script("document.querySelector('a[data-modal=\"/User/Login\"]').click();")
        
        time.sleep(2)
        inputs = driver.find_elements(By.TAG_NAME, "input")
        
        email = next((i for i in inputs if (i.get_attribute("type") == "email" or i.get_attribute("name") == "UserName") and i.is_displayed()), None)
        password = next((i for i in inputs if i.get_attribute("type") == "password" and i.is_displayed()), None)
        
        if email and password:
            if not MORLEVI_USER or not MORLEVI_PASS:
                print("❌ שגיאה: חסרים פרטי התחברות במשתני הסביבה")
                return False

            email.clear()
            email.send_keys(MORLEVI_USER)
            password.clear()
            password.send_keys(MORLEVI_PASS)
            password.submit()
            time.sleep(5)
            return True
    except Exception as e:
        print(f"❌ שגיאה בהתחברות: {e}")
    return False

def fetch_shopify_inventory_map():
    print("⏳ טוען תמונת מצב משופיפיי (כולל תגיות וספק)...")
    url = f"https://{SHOPIFY_STORE_URL}/admin/api/2024-01/products.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    params = {"limit": 250, "fields": "id,tags,vendor,variants"}
    
    inventory_map = {}
    
    while True:
        try:
            r = requests.get(url, headers=headers, params=params)
            if r.status_code != 200:
                print(f"⚠️ שגיאת שופיפיי: {r.status_code}")
                break
            
            data = r.json()
            for prod in data.get("products", []):
                tags = prod.get("tags", "")
                vendor = prod.get("vendor", "")
                
                for variant in prod.get("variants", []):
                    sku = str(variant.get("sku")).strip()
                    if sku:
                        inventory_map[sku] = {
                            "variant_id": variant["id"],
                            "inventory_item_id": variant["inventory_item_id"],
                            "price": variant["price"],
                            "qty": variant["inventory_quantity"],
                            "tags": tags,
                            "vendor": vendor
                        }
            
            link = r.headers.get("Link")
            if not link or 'rel="next"' not in link: break
            
            next_url = None
            for part in link.split(','):
                if 'rel="next"' in part:
                    next_url = part.split(';')[0].strip('<> ')
                    break
            if next_url: url = next_url; params = {}
            else: break
            
        except Exception as e:
            print(f"⚠️ שגיאה בטעינת שופיפיי: {e}")
            break
            
    print(f"✅ נטענו {len(inventory_map)} מוצרים מהחנות.")
    return inventory_map

def update_shopify_variant(variant_id, new_price, new_qty):
    url = f"https://{SHOPIFY_STORE_URL}/admin/api/2024-01/variants/{variant_id}.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN, "Content-Type": "application/json"}
    payload = {"variant": {"id": variant_id, "price": new_price, "inventory_quantity": new_qty}}
    try:
        r = requests.put(url, json=payload, headers=headers)
        if r.status_code == 429:
            time.sleep(2)
            return update_shopify_variant(variant_id, new_price, new_qty)
        return r.status_code == 200
    except: return False

def update_shopify_cost(inventory_item_id, cost_price):
    url = f"https://{SHOPIFY_STORE_URL}/admin/api/2024-01/inventory_items/{inventory_item_id}.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN, "Content-Type": "application/json"}
    payload = {"inventory_item": {"id": inventory_item_id, "cost": cost_price}}
    try:
        r = requests.put(url, json=payload, headers=headers)
        if r.status_code == 429:
            time.sleep(1)
            requests.put(url, json=payload, headers=headers)
    except: pass

def calculate_morlevi_price(raw_price):
    if raw_price < 300: return round((raw_price + 50) * 1.18)
    else: return round((raw_price / 0.85) * 1.18)

def get_stock_level(text):
    if "זמין במלאי" in text: return 10
    if "זמינות מוגבלת" in text: return 3
    return 0

def sync_products():
    if not SHOPIFY_ACCESS_TOKEN:
        print("❌ שגיאה: חסר טוקן שופיפיי")
        return

    driver = init_driver()
    try:
        if not login_to_morlevi(driver): return

        # 1. טעינת נתונים משופיפיי
        shopify_map = fetch_shopify_inventory_map()
        if not shopify_map: return

        # 2. סריקת מור לוי
        print(f"🔄 סורק את הכתובת: {START_URL}")
        driver.get(START_URL)
        time.sleep(5)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)
        
        elems = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
        links = list(set([e.get_attribute('href') for e in elems]))
        print(f"🔎 נמצאו {len(links)} מוצרים בדף הספק.")

        updated_count = 0
        zeroed_count = 0
        found_skus_on_site = set()

        # 3. לולאת עדכון (עוברת על המוצרים שנמצאו באתר)
        for i, link in enumerate(links):
            try:
                driver.get(link)
                clean_ui(driver)
                
                sku = ""
                try: sku = driver.find_element(By.CSS_SELECTOR, ".sku-copy:not(.ltr)").get_attribute("data-sku")
                except: pass
                if not sku:
                    try: sku = driver.find_element(By.CSS_SELECTOR, ".sku-copy.ltr").get_attribute("data-sku")
                    except: pass
                sku = str(sku).strip()
                
                if sku: found_skus_on_site.add(sku)
                
                if sku not in shopify_map: continue

                # בדיקות מקדימות לחיסכון בזמן
                curr = shopify_map[sku]
                
                # בודקים אם המוצר הוא של Morlevi ואם יש לו תגית MOR
                if curr['vendor'] != VENDOR_NAME or TARGET_TAG not in curr['tags']:
                    continue

                supplier_price_raw = 0
                try:
                    p_text = driver.find_element(By.ID, "basicPrice").text
                    supplier_price_raw = float(re.sub(r"[^\d.]", "", p_text))
                except: pass
                
                supplier_qty = 0
                try:
                    stock_text = driver.find_element(By.CLASS_NAME, "stockMsg").text
                    supplier_qty = get_stock_level(stock_text)
                except: pass

                final_price = str(calculate_morlevi_price(supplier_price_raw))
                
                if float(final_price) != float(curr["price"]) or supplier_qty != int(curr["qty"]):
                    print(f"[{i+1}] ♻️ מעדכן {sku}: מחיר {curr['price']}->{final_price}, מלאי {curr['qty']}->{supplier_qty}")
                    if update_shopify_variant(curr["variant_id"], final_price, supplier_qty):
                        if supplier_price_raw > 0:
                            update_shopify_cost(curr["inventory_item_id"], supplier_price_raw)
                        updated_count += 1
                        
            except Exception as e:
                print(f"⚠️ שגיאה במוצר {i}: {e}")

        # 4. איפוס מוצרים שנעלמו (Zero Out) - לוגיקה משולבת
        print("\n🧹 בודק מוצרים (Morlevi + תגית MOR) שנעלמו מהספק...")
        for sku, data in shopify_map.items():
            
            # תנאי 1: הספק הוא Morlevi
            if data['vendor'] != VENDOR_NAME:
                continue
            
            # תנאי 2: יש תגית MOR
            if TARGET_TAG not in data['tags']:
                continue
            
            # תנאי 3: לא נמצא בסריקה + יש מלאי
            if sku not in found_skus_on_site and int(data['qty']) > 0:
                print(f"   🚫 מוצר {sku} נעלם מהספק. מאפס מלאי.")
                if update_shopify_variant(data['variant_id'], data['price'], 0):
                    zeroed_count += 1

        print(f"\n🏁 סיכום:")
        print(f"   - עודכנו: {updated_count}")
        print(f"   - אופסו ל-0: {zeroed_count}")

    finally:
        driver.quit()

if __name__ == "__main__":
    sync_products()
