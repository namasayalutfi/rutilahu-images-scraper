import os
import time
import json
import requests
from urllib.parse import quote_plus
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================
# CONFIG
# ==========================================
SAVE_FOLDER = r"C:\Users\Lutfi\Documents\Project\AITF\data_citra_mkn"

QUERIES = [
    "rumah tidak layak huni indonesia",
    "rumah reyot indonesia",
    "rumah kumuh indonesia",
    "hunian tidak layak indonesia",
    "perumahan miskin indonesia",
    "slum house indonesia",
    "poor house indonesia"
]

LIMIT = 1000
MIN_SIZE_KB = 30

if not os.path.exists(SAVE_FOLDER):
    os.makedirs(SAVE_FOLDER)

# ==========================================
# CHROME SETUP
# ==========================================
chrome_options = Options()
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument("user-agent=Mozilla/5.0")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=chrome_options
)

downloaded_count = 1
used_urls = set()

try:
    for query in QUERIES:

        if downloaded_count > LIMIT:
            break

        print(f"\nMencari gambar di Bing untuk: {query}")

        search_url = f"https://www.bing.com/images/search?q={quote_plus(query)}&form=HDRSC2"
        driver.get(search_url)
        time.sleep(3)

        # ==========================================
        # SCROLLING
        # ==========================================
        last_count = 0
        scroll_tries = 0

        while scroll_tries < 20:
            driver.execute_script("window.scrollBy(0, 2000);")
            time.sleep(2)

            elements = driver.find_elements(By.CLASS_NAME, "iusc")
            current_count = len(elements)

            print(f"Thumbnail ditemukan: {current_count}")

            if current_count == last_count:
                scroll_tries += 1
            else:
                scroll_tries = 0

            last_count = current_count

            if current_count > 500:
                break

        # ==========================================
        # DOWNLOAD
        # ==========================================
        print("Memulai download...")

        elements = driver.find_elements(By.CLASS_NAME, "iusc")

        for el in elements:

            if downloaded_count > LIMIT:
                break

            try:
                m_data = el.get_attribute("m")
                if not m_data:
                    continue

                json_data = json.loads(m_data)
                img_url = json_data.get("murl")

                if not img_url or not img_url.startswith("http"):
                    continue

                if img_url in used_urls:
                    continue

                response = requests.get(img_url, timeout=10)
                img_data = response.content
                file_size = len(img_data) / 1024

                if file_size < MIN_SIZE_KB:
                    continue

                file_name = f"rutilahu_{downloaded_count:04d}.jpg"
                file_path = os.path.join(SAVE_FOLDER, file_name)

                with open(file_path, "wb") as f:
                    f.write(img_data)

                print(f"[{downloaded_count}/{LIMIT}] Saved ({file_size:.1f} KB)")

                used_urls.add(img_url)
                downloaded_count += 1

            except Exception:
                continue

    print(f"\nSelesai! Total berhasil: {downloaded_count - 1}")

finally:
    driver.quit()