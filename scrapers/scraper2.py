from playwright.sync_api import sync_playwright
from urllib.parse import urljoin, urlparse
from hashlib import md5
import os
import time
import requests
import re

script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, "output")
os.makedirs(output_dir, exist_ok=True)

media_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.tiff', '.ico',
                    '.mp3', '.wav', '.ogg', '.mp4', '.webm', '.pdf', '.json'}

def get_links_from_page(page, base_url):
    raw_links = page.eval_on_selector_all("a[href]", "elements => elements.map(el => el.href)")
    clean_links = set()
    media_links = set()
    for link in raw_links:
        absolute = urljoin(base_url, link)
        if absolute.startswith("http"):
            if any(absolute.lower().endswith(ext) for ext in media_extensions):
                media_links.add(absolute)
            else:
                clean_links.add(absolute)
    return clean_links, media_links

def save_file_from_url(url, save_dir):
    try:
        os.makedirs(save_dir, exist_ok=True)
        filename = os.path.basename(urlparse(url).path) or "file"
        file_path = os.path.join(save_dir, filename)
        if os.path.exists(file_path):
            return
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, stream=True, timeout=10)
        response.raise_for_status()
        with open(file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception as e:
        print(f"Failed to download {url}: {e}")

def clean_text(text):
    text = re.sub(r'[:;]-?[)D]', '', text)
    text = re.sub(r'\$?call', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\n{2,}', '\n', text)
    drop_words = [
        "Small", "Medium", "Large", "XL", "S-3", "M 6-8", "15-20", "Extra Large",
        "Prices and food menu items availability are subject to change without notice.",
        "To order, please call", "Latest menu", "confirm and order"
    ]
    for word in drop_words:
        text = text.replace(word, '')
    return text.strip()

def get_page_text_and_links(playwright, url):
    browser = None
    try:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1"
            }
        )
        page = context.new_page()
        page.goto(url, timeout=30000)
        page.wait_for_load_state("networkidle")

        domain = urlparse(url).netloc.replace(":", "_")
        save_dir = os.path.join(output_dir, "download", domain)
        os.makedirs(save_dir, exist_ok=True)

        url_hash = md5(url.encode()).hexdigest()[:8]
        screenshot_path = os.path.join(save_dir, f"screenshot_{url_hash}.png")
        page.screenshot(path=screenshot_path, full_page=True)

        text = page.inner_text("body")
        links, media_links = get_links_from_page(page, url)

        for media_url in media_links:
            save_file_from_url(media_url, save_dir)

        return text, links
    except Exception as e:
        print(f"Failed to scrape {url}: {e}")
        return "", set()
    finally:
        if browser:
            browser.close()

def scrape_with_depth(playwright, start_url, max_depth):
    visited = set()
    text_data = []
    to_visit = [(start_url, 0)]
    main_domain = urlparse(start_url).netloc.replace("www.", "")

    while to_visit:
        current_depth = to_visit[0][1]
        print(f"\nDepth {current_depth}\n")

        current_level_tasks = []
        remaining = []

        for url, depth in to_visit:
            if depth == current_depth:
                current_level_tasks.append((url, depth))
            else:
                remaining.append((url, depth))

        to_visit = remaining

        unique_pending_links = {
            url for url, depth in current_level_tasks
            if url not in visited and not any(url.lower().endswith(ext) for ext in media_extensions)
        }
        total = len(unique_pending_links)
        count = 1

        for current_url, depth in current_level_tasks:
            if current_url in visited or depth > max_depth:
                continue

            current_domain = urlparse(current_url).netloc.replace("www.", "")
            start_time = time.time()
            text, links = get_page_text_and_links(playwright, current_url)
            end_time = time.time()
            elapsed = end_time - start_time

            if current_url in unique_pending_links:
                print(f"Scraping ({count}/{total}) [{elapsed:.2f}s]: {current_url}")
                count += 1
            else:
                print(f"Skipping: {current_url}")

            text_data.append([current_url, text])
            visited.add(current_url)

            if depth < max_depth:
                for link in links:
                    link_domain = urlparse(link).netloc.replace("www.", "")
                    if link not in visited and not any(link.lower().endswith(ext) for ext in media_extensions):
                        if link_domain == main_domain or depth == 0:
                            to_visit.append((link, depth + 1))

    return text_data

if __name__ == "__main__":
    website = "https://www.yuseafood.com/yorkdalehome"                        # url
    scrape_depth = 2 

    with sync_playwright() as playwright:
        scraped_data = scrape_with_depth(playwright, website, scrape_depth)

    output_file = os.path.join(output_dir, "scraped_text.txt")
    with open(output_file, "a", encoding="utf-8") as file:
        for url, text in scraped_data:
            cleaned = clean_text(text)
            file.write(f"URL: {url}\n")
            file.write("Text:\n")
            file.write(cleaned + "\n")
            file.write("=" * 100 + "\n\n")

    print("Complete.")
