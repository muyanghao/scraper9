
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin, urlparse
from pyfiglet import Figlet
from rich.console import Console
import os
import time
import re
import requests
import argparse
import threading
import random
import hashlib
from urllib.parse import urldefrag
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
import signal
import sys

# pip install playwright rich pyfiglet requests
# playwright install

record_lock = threading.Lock()
fail_lock = threading.Lock()


UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
]
UA = random.choice(UA_LIST)

FORCE_FETCH_HEADLESS = False
BOT_KEYWORDS = ["verify you are human"]

FORCE_FETCH_TIMEOUT = 5
FORCE_FETCH_HTML_LEN = 12000

flush_interval = 100
console = Console()

downloadable_extensions = {'.pdf', '.zip', '.rar', '.7z', '.doc', '.docx', '.xls', '.xlsx', '.exe', ".csv", ".json", ".ovpn"}
SKIP_KEYWORDS = ["pdf", "document", "calendar", "login", "signin", "file", "list", "download", "/media/", "upload", ".xlsx", "docx", ".doc"]

class PauseController:
    def __init__(self, key='h'):
        self.key = key.lower()
        self.paused = False
        self._lock = threading.Lock()
        self._stop = False
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _worker(self):
        try:
            import msvcrt
            while not self._stop:
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch and ch.lower() == self.key:
                        with self._lock:
                            self.paused = not self.paused
                        print("\n[PAUSED] Press 'h' to resume..." if self.paused else "\n[RESUMED]")
                        time.sleep(0.3)
                time.sleep(0.05)
        except ImportError:
            import select
            import termios
            import tty
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)
                while not self._stop:
                    dr, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if dr:
                        ch = sys.stdin.read(1)
                        if ch and ch.lower() == self.key:
                            with self._lock:
                                self.paused = not self.paused
                            print("\n[PAUSED] Press 'h' to resume..." if self.paused else "\n[RESUMED]")
                            time.sleep(0.3)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def wait_if_paused(self):
        while True:
            with self._lock:
                paused = self.paused
            if not paused:
                break
            time.sleep(0.2)

    def stop(self):
        self._stop = True

pause_controller = PauseController(key='h')

script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, "output")
os.makedirs(output_dir, exist_ok=True)
parser = argparse.ArgumentParser(description="SCRAPER9 Web Crawler")
parser.add_argument("-hl", "--headless", action="store_true", default=True, help="Use headless browser in all modes")
parser.add_argument("-u", "--url", type=str, help="Path to .txt file containing list of websites (one per line)")
parser.set_defaults(contacts=True, txt=True)
contacts_group = parser.add_mutually_exclusive_group()
contacts_group.add_argument("-c", "--contacts", dest="contacts", action="store_true", help="Enable contact extraction")
contacts_group.add_argument("-nc", "--no-contacts", dest="contacts", action="store_false", help="Disable contact extraction")
txt_group = parser.add_mutually_exclusive_group()
txt_group.add_argument("-txt", "--txt", dest="txt", action="store_true", help="Enable TXT output")
txt_group.add_argument("-nt", "--no-txt", dest="txt", action="store_false", help="Disable TXT output")
parser.add_argument("-d", "--depth", type=int, default=2, help="Crawl depth level")
parser.add_argument("-pdf", "--pdf", action="store_true", default=False, help="Enable PDF download(If open with -mo, it will download the pdf with mayor)")
parser.add_argument("-da", "--download-all", action="store_true", default=False, help="Download all downloadable files")
parser.add_argument("-ss", "--screenshot", action="store_true", default=False, help="Enable screenshot saving")
parser.add_argument("-mo", "--mayor-only", action="store_true", help="Only extract contacts with 'mayor' in email")
parser.add_argument("-cb", "--combine", action="store_true", default=False, help="Combine all output txt into one file")
parser.add_argument("-img", "--image", action="store_true", default=False, help="Enable download all images")
parser.add_argument("-t", "--threads", type=int, default=3, help="Number of concurrent threads when using --url")
main_domain_group = parser.add_mutually_exclusive_group()
main_domain_group.add_argument("-md", "--main-domain", dest="main_domain", action="store_true", help="Restrict to main domain")
main_domain_group.add_argument("-nmd", "--no-main-domain", dest="main_domain", action="store_false", help="Allow crawling outside main domain")
parser.set_defaults(main_domain=False)
args = parser.parse_args()

url1 = args.url
use_headless_browser = args.headless
enable_image_download = args.image
combine_txt = args.combine
mayor_only_filter = args.mayor_only
scrape_depth = args.depth
enable_pdf_download = args.pdf
enable_download_all = args.download_all
enable_screenshot_saving = args.screenshot
enable_contact_extraction = args.contacts
enable_txt_output = args.txt
restrict_to_main_domain = args.main_domain
social_domains = {"facebook.com", "instagram.com", "www.linkedin.com", "youtube.com", "twitter.com", "tiktok.com", "x.com"}

def load_existing_contacts(contact_file):
    seen_emails = set()
    seen_phones = set()
    if os.path.exists(contact_file):
        with open(contact_file, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("$")
                if len(parts) >= 2:
                    seen_emails.add(parts[1])
                    if len(parts) > 2:
                        for phone in parts[2:]:
                            seen_phones.add(phone)
    return seen_emails, seen_phones

def download_file(url, save_dir):
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": UA})
        if r.status_code == 200:
            filename = url.split("/")[-1].split("?")[0]
            if not filename:
                filename = "file_" + str(int(time.time()))
            path = os.path.join(save_dir, filename)
            with open(path, 'wb') as f:
                f.write(r.content)
            print(f"Downloaded: {path}")
    except Exception as e:
        console.print(f"Failed to download: {url} - {e}", style="bold red")
def download_pdf(url, save_dir):
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": UA})
        if r.status_code == 200:
            filename = url.split("/")[-1].split("?")[0]
            if not filename.lower().endswith(".pdf"):
                filename += ".pdf"
            path = os.path.join(save_dir, filename)
            with open(path, 'wb') as f:
                f.write(r.content)
            print(f"Saved PDF: {path}")
    except Exception as e:
        print(f"Failed to download PDF: {url} - {e}")

def normalize_phone(phone):
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return None

def extract_phones(text):
    phone_patterns = [
        r'\+?\d{1,3}[\s\.-]?\(?\d{3}\)?[\s\.-]?\d{3}[\s\.-]?\d{4}',
        r'\(\d{3}\)[\s\.-]?\d{3}[\s\.-]?\d{4}',
        r'\d{3}[\s\.-]\d{3}[\s\.-]\d{4}',
        r'\d{3}\.\d{3}\.\d{4}',
        r'\b\d{10}\b'
    ]
    all_matches = set()
    for pattern in phone_patterns:
        for match in re.findall(pattern, text):
            norm = normalize_phone(match)
            if norm:
                all_matches.add(norm)
    return sorted(all_matches)

def looks_like_name(local):
    clean_local = re.sub(r'\d+', '', local)
    non_name_keywords = {"lcook", "dpickles", "mnagy", "citizen", "citizensfirst", "contactus", "ctbpayables", "STATCAN", "access", "accounting", "accounts", "admin", "adminsupport", "applications", "aquatics", "arts", "artsawards", "auditorgeneral", "backflow", "billing", "booking", "budget", "building", "buildingpermits", "buildingservices", "bylaw", "care", "career", "careers", "chair", "childcare", "city", "citymanager", "claims", "clerk", "clerks", "clinic", "committee", "communications", "community", "complaints", "construction", "contact", "contactus", "corporatecommunications", "council", "councillor", "courtservices", "covid", "customer", "customerservice", "dev", "developer", "development", "digital", "dispatch", "donotreply", "economicdevelopment", "elections", "emergency", "employment", "enforcement", "engineering", "environment", "event", "events", "feedback", "festival", "finance", "fire", "fleet", "forestry", "general", "gis", "health", "hello", "help", "helpdesk", "heritage", "hospital", "housing", "hr", "humanresources", "info", "infotech", "infrastructure", "inquiry", "inspection", "integrity", "it", "jobs", "library", "licensing", "litigation", "mail", "mayor", "mayorscall", "media", "mediahotline", "municipal", "museum", "music", "network", "news", "newsletter", "noreply", "office", "ombudsman", "pandemic", "parking", "parks", "payment", "payroll", "permit", "planning", "plumbing", "police", "portal", "postmaster", "pr", "press", "privacy", "procurement", "public", "publichealth", "purchasing", "readstc", "realty", "realtyservices", "recreation", "region", "reply", "request", "rescue", "reservations", "roads", "sales", "security", "service", "servicedesk", "sewer", "smartcommute", "social", "socialmedia", "specialevents", "sports", "stadiumrentals", "stormwater", "street", "streetlighting", "support", "supportdesk", "system", "tax", "team", "tech", "tickets", "town", "traffic", "transit", "transportation", "volunteer", "voter", "ward", "waste", "water", "web", "webmaster", "wellness", "youth", "zoning"}
    if any(kw == clean_local.lower() or clean_local.lower().startswith(kw)
           for kw in non_name_keywords):
        return False
    if '.' in clean_local or '_' in clean_local or '-' in clean_local:
        return True
    return clean_local.isalpha() and len(clean_local) > 3

def email_to_name(local):
    clean_local = re.sub(r'\d+', '', local)
    parts = re.split(r'[._-]+', clean_local)
    parts = [p for p in parts if p.isalpha()]
    return " ".join(p.capitalize() for p in parts) if parts else "Unknown"

def extract_contacts(text):
    emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    names = re.findall(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', text)
    results = []
    for match in re.finditer(r'[\w\.-]+@[\w\.-]+\.\w+', text):
        email = match.group()
        local = email.split("@")[0]
        start = max(0, match.start() - 200)
        end = min(len(text), match.end() + 200)
        context = text[start:end]
        phones = extract_phones(context)
        if looks_like_name(local):
            name = email_to_name(local)
        else:
            match_name = next((n for n in names if local.lower() in n.lower().replace(" ", "")), None)
            name = match_name or "Unknown"
        results.append((name, email, phones))
    return results

media_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.tiff', '.ico', '.mp3', '.wav', '.ogg', '.mp4', '.webm', '.json', '.pdf'}

def get_links_from_page(page, base_url):
    calendar_keywords = ["StartDate=", "EndDate=", "calendar", "event", "schedule", "MeetingDate=", "index?"]
    raw_links = page.eval_on_selector_all("a[href]", "elements => elements.map(el => el.href)")
    clean_links = set()
    media_links = set()
    for link in raw_links:
        absolute = urljoin(base_url, link)
        if absolute.startswith("http"):
            if any(keyword in absolute for keyword in calendar_keywords):
                continue
            if any(absolute.lower().endswith(ext) for ext in media_extensions):
                media_links.add(absolute)
            else:
                clean_links.add(absolute)
    return clean_links, media_links

def get_safe_filename(url, save_dir=None, max_length=100):
    filename = url.replace("https://", "").replace("http://", "")
    filename = re.sub(r'[^A-Za-z0-9._-]', '_', filename)

    if len(filename) > max_length:
        hash_part = hashlib.md5(url.encode('utf-8')).hexdigest()
        filename = "longurl_" + hash_part

        # txt_path = os.path.join(save_dir, filename + "_url.txt")
        # if not os.path.exists(txt_path):
            # with open(txt_path, "w", encoding="utf-8") as f:
            #     f.write(url + "\n")

    return filename

def looks_like_bot_check(text: str) -> bool:
    low = text.lower()
    if any(kw in low for kw in BOT_KEYWORDS):
        return True
    if len(text.strip()) < 200 and ("checking" in low or "verify" in low):
        return True
    return False

def force_fetch_after_block(playwright, url, screenshot_dir=None):
    browser = None
    try:
        browser = playwright.chromium.launch(
            headless=FORCE_FETCH_HEADLESS or use_headless_browser,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(user_agent=UA, viewport={"width": 1, "height": 1})
        page = context.new_page()
        page.goto(url, timeout=60000)

        start = time.time()
        page.wait_for_timeout(1000)
        while True:
            try:
                html = page.content()
                html_len = len(html)
            except Exception:
                html = ""
                html_len = 0

            if html_len > FORCE_FETCH_HTML_LEN:
                console.print(f"[FORCE-FETCH] success", style="bold green")
                text = page.inner_text("body")
                links, _ = get_links_from_page(page, url)
                if screenshot_dir and enable_screenshot_saving:
                    filename = os.path.join(screenshot_dir, get_safe_filename(url, screenshot_dir) + "_force.png")
                    page.screenshot(path=filename, full_page=True)
                return text, links

            if time.time() - start > FORCE_FETCH_TIMEOUT:
                try:
                    text_final = page.inner_text("body")
                except Exception:
                    text_final = ""
                links, _ = get_links_from_page(page, url)
                return text_final, links

            page.wait_for_timeout(300)
    except Exception as e:
        console.print(f"[FORCE-FETCH] Failed: {e}", style="bold red")
        return "", set()
    finally:
        if browser:
            browser.close()

def solve_bot_and_get(playwright, url, screenshot_dir=None):
    browser = None
    try:
        browser = playwright.chromium.launch(headless=use_headless_browser, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(user_agent=UA, viewport={"width": 1, "height": 1})
        page = context.new_page()
        page.goto(url, timeout=60000)
        page.wait_for_timeout(1000)
        start = time.time()
        while True:
            try:
                html_length = len(page.content())
            except Exception:
                html_length = 0
            if html_length > 12000:
                print(f"[BOT-DETECTION] Page content loaded (length={html_length})")
                break
            if time.time() - start > 15:
                console.print("[BOT-DETECTION] Timeout 15s reached.", style="bold red")
                break
            page.wait_for_timeout(500)
        text = page.inner_text("body")
        if screenshot_dir and enable_screenshot_saving:
            filename = os.path.join(screenshot_dir, get_safe_filename(url, screenshot_dir) + "_solved.png")
            page.screenshot(path=filename, full_page=True)
        links, _ = get_links_from_page(page, url)
        return text, links
    except Exception as e:
        console.print(f"[BOT-DETECTION] Failed to solve bot page: {e}", style="bold red")
        return "", set()
    finally:
        if browser:
            browser.close()

EMAIL_REGEX = re.compile(r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}")
NAME_REGEX = re.compile(r"[A-Z][a-z]+\s+[A-Z][a-z]+")
PHONE_REGEX = re.compile(r"(?:(?:\+?1\s*(?:[.-]\s*)?)?(?:\(?\d{3}\)?|\d{3})\s*(?:[.-]\s*)?)?\d{3}\s*(?:[.-]\s*)?\d{4}")
KEYWORDS_URL = ["mayor", "reeve", "council", "directory", "contact", "elected-officials", "town-hall", "government", "staff"]
KEYWORDS_NAME = ["mayor", "reeve", "councillor", "council"]


def get_page_text_and_links(playwright, url, screenshot_dir=None):
    if any(keyword in url.lower() for keyword in SKIP_KEYWORDS):
        console.print(f"[SKIP BROWSER] URL contains skip keyword: {url}", style="bold yellow")
        return "", set()
    browser = None
    try:

        browser = playwright.chromium.launch(
            headless=use_headless_browser, 
            args=[
                "--disable-blink-features=AutomationControlled", 
                # "--windows-size=1280,800"
            ]
        )

        context = browser.new_context(
            user_agent=UA, 
            viewport={"width": 1, "height": 1}
        )

        page = context.new_page()
        page.goto(url, timeout=15000)

        page.wait_for_function("document.readyState === 'complete'", timeout=15000)

        html = page.content()

        found_emails = list(re.finditer(EMAIL_REGEX, html))
        all_email_texts = set([m.group(0) for m in found_emails])

        html_lower = html.lower()
        nearest_email = None
        min_distance = float("inf")
        nearest_email_index = -1

        for match in re.finditer(r"mayor|reeve", html_lower):
            mayor_pos = match.start()
            for i, email_match in enumerate(found_emails):
                email_pos = email_match.start()
                dist = abs(email_pos - mayor_pos)
                if dist < min_distance:
                    min_distance = dist
                    nearest_email = email_match.group(0)
                    nearest_email_index = i

        city = get_safe_filename(url, "output")
        domain_part = urlparse(url).netloc.replace("www.", "").replace(".", "_")
        output_path = os.path.join(output_dir, "mayors.txt")
        os.makedirs("output", exist_ok=True)
        with open(output_path, "a+", encoding="utf-8") as f:
            f.seek(0)
            content = f.read()

            if nearest_email:
                email_span = found_emails[nearest_email_index].span()
                context_start = max(0, email_span[0] - 2000)
                context_end = min(len(html), email_span[1] + 1000)
                nearest_context = html[context_start:context_end]

                phone_matches = re.findall(PHONE_REGEX, nearest_context)
                phone = phone_matches[0] if phone_matches else ""

                name_matches = re.findall(NAME_REGEX, html[context_start:email_span[0]])
                name = name_matches[-1] if name_matches else "Unknown"

                if nearest_email not in content:
                    f.write(f"{domain_part}${name}${nearest_email}${phone}\n")

            mayor_emails = [email for email in all_email_texts if "mayor" in email.lower() or "reeve" in email.lower()]
            for email in mayor_emails:
                if email != nearest_email:
                    if email not in content:
                        f.write(f"{domain_part}$mayor${email}$\n")

        links, _ = get_links_from_page(page, url)
        return "", links

    except Exception as e:
        console.print(f"Failed to scrape {url}: {e}", style="bold red")
        try:
            return force_fetch_after_block(playwright, url, screenshot_dir)
        except Exception:
            return "", set()
    finally:
        if browser:
            browser.close()


def basic_request_text_and_links(playwright, url, screenshot_dir=None):
    if any(keyword in url.lower() for keyword in SKIP_KEYWORDS):
        console.print(f"[SKIP BROWSER] URL contains skip keyword: {url}", style="bold yellow")
        return "", set()
    browser = None
    try:
        try:
            head = requests.head(url, timeout=15, allow_redirects=True, headers={"User-Agent": UA})
            if head.status_code in [403, 404]:
                console.print(f"[HEAD {head.status_code}] Try force fetch: {url}", style="bold yellow")
                return force_fetch_after_block(playwright, url, screenshot_dir)
            if head.status_code in [401, 500]:
                console.print(f"Skipping {url}: HTTP {head.status_code}", style="bold red")
                return "", set()
        except requests.exceptions.RequestException as e:
            console.print(f"[HEAD ERROR] {e} -> Try force fetch: {url}", style="bold yellow")
            return force_fetch_after_block(playwright, url, screenshot_dir)

        browser = playwright.chromium.launch(headless=use_headless_browser, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(user_agent=UA, viewport={"width": 1, "height": 1})
        page = context.new_page()
        page.goto(url, timeout=15000)
        try:
            page.wait_for_function("document.readyState === 'complete'", timeout=15000)
        except:
            page.wait_for_timeout(15000)
        page.wait_for_load_state("domcontentloaded")
        if screenshot_dir and enable_screenshot_saving:
            filename = os.path.join(screenshot_dir, get_safe_filename(url) + ".png")
            page.screenshot(path=filename, full_page=True)
        text = page.inner_text("body")
        if looks_like_bot_check(text):
            browser.close()
            browser = None
            return solve_bot_and_get(playwright, url, screenshot_dir)

        links, _ = get_links_from_page(page, url)
        return text, links
    except Exception as e:
        console.print(f"Failed to scrape {url}: {e}", style="bold red")
        try:
            return force_fetch_after_block(playwright, url, screenshot_dir)
        except Exception:
            return "", set()
    finally:
        if browser:
            browser.close()

def save_all_images_from_page(html, base_url, save_dir="images"):
    os.makedirs(save_dir, exist_ok=True)
    soup = BeautifulSoup(html, "html.parser")
    img_tags = soup.find_all("img")
    count = 0

    for img in img_tags:
        src = img.get("src")
        if not src:
            continue
        img_url = urljoin(base_url, src)

        try:
            response = requests.get(img_url, timeout=10, headers={"User-Agent": UA})
            if response.status_code == 200 and response.content:
                ext = os.path.splitext(img_url)[-1]
                if not ext or len(ext) > 5:
                    ext = ".jpg"
                filename = f"img_{count}{ext}"
                filepath = os.path.join(save_dir, filename)
                with open(filepath, "wb") as f:
                    f.write(response.content)
                print(f"[IMG] Saved: {filepath}")
                count += 1
        except Exception as e:
            print(f"[IMG] Failed: {img_url} - {e}")

def save_contacts_to_file(contact_file, seen_emails, seen_phones, data):
    with open(contact_file, "a", encoding="utf-8") as contact_out:
        for url, text in data:
            name_email_pairs = extract_contacts(text)
            for name, email, phones in name_email_pairs:
                unique_phones = [p for p in phones if p not in seen_phones]
                if email not in seen_emails:
                    contact_out.write(f"{name}${email}${'$'.join(unique_phones)}\n")
                    seen_emails.add(email)
                    seen_phones.update(unique_phones)


def scrape_with_depth(playwright, start_url, max_depth, contact_file=None):
    visited = set()
    text_data = []
    to_visit = [(start_url, 0)]
    main_domain = urlparse(start_url).netloc.replace("www.", "")
    city_prefix = main_domain.split(".")[0].capitalize()
    screenshots_dir = os.path.join(output_dir, main_domain) if enable_screenshot_saving else None
    pdf_dir = os.path.join(output_dir, main_domain, "pdfs") if enable_pdf_download else None
    if screenshots_dir:
        os.makedirs(screenshots_dir, exist_ok=True)
    if pdf_dir:
        os.makedirs(pdf_dir, exist_ok=True)

    seen_emails = set()
    seen_phones = set()
    counter = 0
    max_depth_reached = 0

    def extract_all_contacts(text):
        contacts = []
        for match in re.finditer(r'[\w\.-]+@[\w\.-]+\.\w+', text):
            email = match.group()
            start = max(0, match.start() - 1500)
            end = match.end() + 500
            context = text[start:end]
            phones = extract_phones(context)
            name_match = re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+', context)
            name = name_match.group() if name_match else "Unknown"
            contacts.append((name, email, phones))
        return contacts

    while to_visit:
        current_depth = to_visit[0][1]
        if current_depth <= max_depth:
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
            urldefrag(url).url for url, depth in current_level_tasks
            if url not in visited and not any(url.lower().endswith(ext) for ext in media_extensions)
        }
        total = len(unique_pending_links)
        count = 1

        for current_url, depth in current_level_tasks:
            current_url = urldefrag(current_url).url
            pause_controller.wait_if_paused()
            if current_url in visited or depth > max_depth:
                continue

            if mayor_only_filter and depth >= 1:
                if not any(k in current_url.lower() for k in KEYWORDS_URL):
                    continue

            start_time = time.time()
            if mayor_only_filter:
                text, links = get_page_text_and_links(playwright, current_url, screenshot_dir=screenshots_dir)
            else:
                text, links = basic_request_text_and_links(playwright, current_url, screenshot_dir=screenshots_dir)

            if enable_pdf_download and current_url.lower().endswith(".pdf") and pdf_dir:
                if not mayor_only_filter or (mayor_only_filter and any(k in current_url.lower() for k in KEYWORDS_URL)):
                    download_pdf(current_url, pdf_dir)

            end_time = time.time()
            elapsed = end_time - start_time
            console.print(f"Scraping ({count}/{total}) [{elapsed:.2f}s]: {current_url}", style="green")
            count += 1

            if depth > max_depth_reached:
                max_depth_reached = depth

            if mayor_only_filter:
                contact_snippets = extract_all_contacts(text)
                for name, email, phones in contact_snippets:
                    if email not in seen_emails:
                        line = f"{city_prefix}${name}${email}${'$'.join(phones)}"
                        text_data.append([current_url, line])
                        seen_emails.add(email)
                        seen_phones.update(phones)
            else:
                text_data.append([current_url, text])

                if enable_image_download:
                    image_dir = os.path.join(output_dir, "images")
                    save_all_images_from_page(text, current_url, image_dir)

            visited.add(current_url)
            counter += 1

            if contact_file and counter % flush_interval == 0:
                save_contacts_to_file(contact_file, seen_emails, seen_phones, text_data)
                text_data = []
                print(f"[Auto-Save] {counter} pages.")

            if depth < max_depth:
                for link in links:
                    link = urldefrag(link).url
                    link_domain = urlparse(link).netloc.replace("www.", "")
                    if link in visited:
                        continue
                    if any(link.lower().endswith(ext) for ext in media_extensions):
                        continue
                    if restrict_to_main_domain and link_domain != main_domain and depth != 0:
                        continue

                    if mayor_only_filter and depth >= 0:
                        if not any(k in link.lower() for k in KEYWORDS_URL):
                            continue

                    next_depth = depth + 1 if link_domain not in social_domains else max_depth + 1
                    to_visit.append((link, next_depth))

    if args.url and max_depth_reached == 0:
        fail_path = os.path.join(output_dir, "fail.txt")
        with open(fail_path, "a", encoding="utf-8") as f:
            f.write(start_url + "\n")

    return text_data, seen_emails, seen_phones

def print_config():
    fig = Figlet(font='slant')
    console = Console()
    console.print(fig.renderText('SCRAPER9'), style="bold black")
    config_items = [
        ("Depth", scrape_depth),
        ("threads", args.threads),
        ("Contacts", enable_contact_extraction and enable_txt_output),
        ("Screenshot", enable_screenshot_saving),
        ("Download PDF", enable_pdf_download),
        ("Main domain", restrict_to_main_domain),
        ("Download all", enable_download_all),
        ("mayor only", mayor_only_filter),
        ("Combine txt", combine_txt),
        ("Download images", enable_image_download),
        ("url path", url1)
    ]
    label_width = max(len(label) for label, _ in config_items)
    for label, value in config_items:
        print(f"{label.ljust(label_width)} --- {value}")
    print("\nPress 'h' anytime to pause/resume.\n")

def scrape_one_site_single(website):
    playwright = sync_playwright().start()
    try:
        scrape_one_site_inner(website, playwright)
    finally:
        playwright.stop()

def scrape_one_site_inner(website, playwright):
    try:
        print(f"Starting scrape for: {website}")
        contact_file = None
        seen_emails, seen_phones = set(), set()

        if enable_contact_extraction and enable_txt_output and not mayor_only_filter:
            domain_part = urlparse(website).netloc.replace("www.", "").replace(".", "_")
            if combine_txt and url1:
                contact_file = os.path.join(output_dir, "combine.txt")
            else:
                contact_file = os.path.join(output_dir, f"contacts_{domain_part}.txt")
            seen_emails, seen_phones = load_existing_contacts(contact_file)
            if not os.path.exists(contact_file):
                open(contact_file, "w").close()

        text_data, seen_emails, seen_phones = scrape_with_depth(
            playwright, website, scrape_depth, contact_file
        )

        if contact_file and text_data:
            save_contacts_to_file(contact_file, seen_emails, seen_phones, text_data)
        print(f"Contacts saved to {contact_file}" if contact_file else "No contacts saved.")

        with record_lock:
            complete_log_path = os.path.join(output_dir, "record_urls.txt")
            with open(complete_log_path, "a", encoding="utf-8") as f:
                f.write(website + "\n")

    except Exception as e:
        with fail_lock:
            fail_log_path = os.path.join(output_dir, "fail_urls.txt")
            with open(fail_log_path, "a", encoding="utf-8") as f:
                f.write(website + "\n")
        print(f"[ERROR] {website} - {e}")


def scrape_one_site(website):
    playwright = sync_playwright().start()
    try:
        print(f"Starting scrape for: {website}")
        contact_file = None
        seen_emails, seen_phones = set(), set()
        if enable_contact_extraction and enable_txt_output and not mayor_only_filter:
            if combine_txt and url1:
                contact_file = os.path.join(output_dir, "combine.txt")
            else:
                contact_file = os.path.join(output_dir, f"{url1}.txt")
            seen_emails, seen_phones = load_existing_contacts(contact_file)
            if not os.path.exists(contact_file):
                open(contact_file, "w").close()

        text_data, seen_emails, seen_phones = scrape_with_depth(
            playwright, website, scrape_depth, contact_file
        )

        if contact_file and text_data:
            save_contacts_to_file(contact_file, seen_emails, seen_phones, text_data)
        print(f"Contacts saved to {contact_file}" if contact_file else "No contacts saved.")

        with record_lock:
            complete_log_path = os.path.join(output_dir, "record_urls.txt")
            with open(complete_log_path, "a", encoding="utf-8") as f:
                f.write(website + "\n")

    except Exception as e:
        with fail_lock:
            fail_log_path = os.path.join(output_dir, "fail_urls.txt")
            with open(fail_log_path, "a", encoding="utf-8") as f:
                f.write(website + "\n")
        print(f"[ERROR] {website} - {e}")

    finally:
        try:
            playwright.stop()
        except:
            pass

if __name__ == "__main__":
    print_config()
    urls = []

    try:
        if args.url:
            with open(args.url, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip()]

            if not urls:
                print("[ERROR] No URLs loaded from file.")
                sys.exit(1)

            max_threads = args.threads

            progress = Progress(
                TextColumn("[bold blue]Batch"),
                BarColumn(bar_width=40),
                "[progress.percentage]{task.percentage:>3.0f}%",
                "•",
                TimeElapsedColumn(),
                "•",
                TimeRemainingColumn(),
                console=console,
                transient=False,
            )
            task = progress.add_task("[green]Scraping websites...", total=len(urls))

            with progress:
                with ThreadPoolExecutor(max_workers=max_threads) as executor:
                    futures = {executor.submit(scrape_one_site, url): url for url in urls}
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as e:
                            print(f"[ERROR] Thread failed: {e}")
                        progress.advance(task)

        else:
            website = input("website: ").strip()
            urls = [website]
            scrape_one_site_single(website)

    except KeyboardInterrupt:
        print("\nBye.")
        sys.exit(0)

    finally:
        pause_controller.stop()
        print("Complete.")
