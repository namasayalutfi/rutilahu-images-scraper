import os
import time
import random
import requests
from urllib.parse import quote_plus
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, ElementClickInterceptedException
from webdriver_manager.chrome import ChromeDriverManager

# ========== CONFIG ==========
SAVE_FOLDER = r"C:\Users\Lutfi\Documents\Project\AITF\mkn_image_dataset"
QUERY = "foto rumah tidak layak huni indonesia"
LIMIT = 250
MIN_SIZE_KB = 30  # minimal file size (KB)
MAX_SCROLL_RETRIES = 12

if not os.path.exists(SAVE_FOLDER):
    os.makedirs(SAVE_FOLDER)

# ========== CHROME OPTIONS ==========
chrome_options = Options()
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
# Optional: kalau mau nampak nyata, jangan headless
# chrome_options.add_argument("--headless=new")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
wait = WebDriverWait(driver, 12)

def save_debug(name_suffix="debug"):
    """Simpan screenshot + page source untuk inspeksi"""
    driver.save_screenshot(os.path.join(SAVE_FOLDER, f"{name_suffix}.png"))
    with open(os.path.join(SAVE_FOLDER, f"{name_suffix}.html"), "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print(f"Saved debug files: {name_suffix}.png / .html")

def get_candidate_src_from_img_elem(img):
    """Coba ambil URL terbaik dari sebuah <img> element (src, data-src, srcset)"""
    for attr in ("src", "data-src", "data-iurl", "data-srcset", "srcset"):
        try:
            val = img.get_attribute(attr)
            if val:
                # kalau srcset, ambil URL pertama yang http
                if attr == "srcset":
                    parts = [p.strip().split(" ")[0] for p in val.split(",")]
                    for p in parts:
                        if p.startswith("http"):
                            return p
                else:
                    return val
        except Exception:
            continue
    return None

def download_image(url, path):
    try:
        resp = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            size_kb = len(resp.content) / 1024
            if size_kb >= MIN_SIZE_KB:
                with open(path, "wb") as f:
                    f.write(resp.content)
                return size_kb
    except Exception:
        pass
    return 0

try:
    search_url = f"https://www.google.com/search?q={quote_plus(QUERY)}&tbm=isch"
    print("Membuka:", search_url)
    driver.get(search_url)

    # coba klik consent jika ada
    try:
        consent = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button#L2AGLb, button[aria-label*='Agree'], button[aria-label*='Terima']"))
        )
        try:
            driver.execute_script("arguments[0].click();", consent)
            print("Consent diklik.")
            time.sleep(1)
        except Exception:
            pass
    except Exception:
        pass

    # tunggu minimal 1 gambar muncul (umum)
    try:
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "img")))
    except TimeoutException:
        print("Tidak ada <img> di halaman (timeout). Simpan debug.")
        save_debug("no_img_after_load")
        driver.quit()
        raise SystemExit("No images found on page.")

    # SCROLLING: ulangi untuk memaksa lazy-load
    last_height = driver.execute_script("return document.body.scrollHeight")
    retries = 0
    while retries < MAX_SCROLL_RETRIES:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(1.2, 2.3))
        # coba klik tombol 'Show more' kalau ada
        try:
            show_btn = driver.find_element(By.CSS_SELECTOR, "input.mye4qd, .mye4qd, div[role='button'][jsname='Y5ANHe']")
            if show_btn.is_displayed():
                try:
                    driver.execute_script("arguments[0].click();", show_btn)
                    print("Clicked 'Show more' button")
                    time.sleep(1.2)
                except Exception:
                    pass
        except Exception:
            pass

        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            retries += 1
        else:
            retries = 0
        last_height = new_height

        # hentikan lebih awal kalau sudah banyak img
        imgs_now = driver.find_elements(By.CSS_SELECTOR, "img")
        if len(imgs_now) > (LIMIT + 120):
            break

    # kumpulkan kandidat thumbnail (fallback: semua img)
    all_imgs = driver.find_elements(By.CSS_SELECTOR, "img")
    print("Total <img> elements found:", len(all_imgs))
    if len(all_imgs) == 0:
        save_debug("no_imgs_final")
        raise SystemExit("No <img> elements found after scrolling.")

    # proses tiap thumbnail: klik -> cari gambar HD di panel kanan (atau fallback ke src)
    count = 1
    seen_urls = set()

    for i, thumb in enumerate(all_imgs):
        if count > LIMIT:
            break

        # dapatkan candidate url dari attribute (thumbnail)
        try:
            candidate = get_candidate_src_from_img_elem(thumb)
        except Exception:
            candidate = None

        # scroll dan klik thumbnail (beberapa elemen butuh scrollIntoView)
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", thumb)
            time.sleep(random.uniform(0.3, 0.9))
            driver.execute_script("arguments[0].click();", thumb)
            time.sleep(random.uniform(1.8, 2.8))
        except (StaleElementReferenceException, ElementClickInterceptedException):
            # kalau gagal klik, skip
            continue
        except Exception:
            # tidak fatal, lanjut
            pass

        # cari gambar resolusi tinggi di DOM: pilih img dengan naturalWidth > 200
        try:
            # jalankan JS untuk mengambil src gambar HD yang terlihat di preview panel
            script = """
            var imgs = Array.from(document.querySelectorAll('img'));
            for (var i=0;i<imgs.length;i++){
                var s = imgs[i].src || imgs[i].getAttribute('data-src') || imgs[i].getAttribute('data-iurl');
                if (!s) continue;
                if (s.startsWith('http') && imgs[i].naturalWidth > 200 && s.indexOf('encrypted')===-1) return s;
            }
            return null;
            """
            hd_url = driver.execute_script(script)
        except Exception:
            hd_url = None

        target_url = None
        if hd_url and hd_url not in seen_urls:
            target_url = hd_url
        else:
            # fallback ke candidate thumbnail URL
            if candidate and candidate.startswith("http") and ("encrypted" not in candidate):
                if candidate not in seen_urls:
                    target_url = candidate

        if not target_url:
            # jika belum dapat, lanjut ke thumbnail berikutnya
            continue

        # coba download
        file_name = f"rutilahu_{count:04d}.jpg"
        file_path = os.path.join(SAVE_FOLDER, file_name)
        size_kb = download_image(target_url, file_path)

        if size_kb >= MIN_SIZE_KB:
            print(f"[{count}/{LIMIT}] Saved: {file_name} ({size_kb:.1f} KB)")
            seen_urls.add(target_url)
            count += 1
        else:
            # hapus file kalau ada tapi kecil
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            # lanjut

    print(f"Done. Total saved: {count-1}")

except Exception as e:
    print("Exception:", str(e))
    save_debug("exception_debug")
finally:
    driver.quit()