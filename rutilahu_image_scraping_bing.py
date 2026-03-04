import os
import time
import json
import csv
import hashlib
import logging
import requests
from datetime import datetime
from urllib.parse import quote_plus
from io import BytesIO
from PIL import Image

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================
# CONFIG
# ==========================================

BASE_FOLDER = r"D:\aitf\data\raw\rutilahu_image_dataset_mkn"
IMAGE_FOLDER = os.path.join(BASE_FOLDER, "images")

QUERIES = [
    "rumah miskin",
    "rumah miskin pedesaan",
    "rumah buruk",
    "rumah warga miskin",
]

LIMIT = 1000
MIN_SIZE_KB = 30
MAX_SCROLL = 20

os.makedirs(IMAGE_FOLDER, exist_ok=True)

SCRAPE_DATE = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ==========================================
# LOGGING SETUP
# ==========================================

log_file = os.path.join(BASE_FOLDER, "scrape_log.txt")

logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logging.info("=== SCRAPING STARTED ===")

# ==========================================
# CHROME SETUP
# ==========================================

chrome_options = Options()
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument("--headless=new")  # Production mode
chrome_options.add_argument("user-agent=Mozilla/5.0")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=chrome_options
)

metadata_list = []
hash_set = set()
downloaded_count = 1

try:
    for query in QUERIES:

        if downloaded_count > LIMIT:
            break

        logging.info(f"Searching: {query}")
        print(f"\nMencari gambar: {query}")

        search_url = f"https://www.bing.com/images/search?q={quote_plus(query)}"
        driver.get(search_url)
        time.sleep(3)

        # ==========================================
        # SCROLLING
        # ==========================================

        last_count = 0
        scroll_tries = 0

        while scroll_tries < MAX_SCROLL:
            driver.execute_script("window.scrollBy(0, 2000);")
            time.sleep(2)

            elements = driver.find_elements(By.CLASS_NAME, "iusc")
            current_count = len(elements)

            if current_count == last_count:
                scroll_tries += 1
            else:
                scroll_tries = 0

            last_count = current_count

        elements = driver.find_elements(By.CLASS_NAME, "iusc")

        # ==========================================
        # DOWNLOAD LOOP
        # ==========================================

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

                response = requests.get(img_url, timeout=10)
                img_data = response.content

                file_size_kb = len(img_data) / 1024
                if file_size_kb < MIN_SIZE_KB:
                    continue

                # ======================================
                # HASH CHECK (DEDUPLICATION)
                # ======================================

                img_hash = hashlib.md5(img_data).hexdigest()

                if img_hash in hash_set:
                    continue

                # ======================================
                # VALIDATE IMAGE
                # ======================================

                image = Image.open(BytesIO(img_data))
                width, height = image.size

                file_name = f"rutilahu_{downloaded_count:05d}.jpg"
                file_path = os.path.join(IMAGE_FOLDER, file_name)

                with open(file_path, "wb") as f:
                    f.write(img_data)

                # ======================================
                # METADATA
                # ======================================

                metadata = {
                    "filename": file_name,
                    "source_url": img_url,
                    "keyword": query,
                    "search_engine": "Bing",
                    "scrape_date": SCRAPE_DATE,
                    "width": width,
                    "height": height,
                    "file_size_kb": round(file_size_kb, 2),
                    "hash_md5": img_hash,
                    "domain": img_url.split("/")[2]
                }

                metadata_list.append(metadata)
                hash_set.add(img_hash)

                print(f"[{downloaded_count}/{LIMIT}] Saved")
                logging.info(f"Saved: {file_name}")

                downloaded_count += 1

            except Exception as e:
                logging.warning(f"Failed image: {str(e)}")
                continue

    # ==========================================
    # SAVE METADATA JSON
    # ==========================================

    json_path = os.path.join(BASE_FOLDER, "metadata.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metadata_list, f, indent=4, ensure_ascii=False)

    # ==========================================
    # SAVE METADATA CSV
    # ==========================================

    csv_path = os.path.join(BASE_FOLDER, "metadata.csv")

    if metadata_list:
        keys = metadata_list[0].keys()
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(metadata_list)

    logging.info("=== SCRAPING FINISHED ===")
    print(f"\nSelesai! Total berhasil: {downloaded_count - 1}")

finally:
    driver.quit()