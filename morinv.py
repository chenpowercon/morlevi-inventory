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

# הגדרות סינון
VENDOR_NAME = "Morlevi"
TARGET_TAG = "MOR"
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
