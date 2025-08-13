from playwright.sync_api import sync_playwright
from urllib.parse import urljoin, urlparse
from pyfiglet import Figlet
from rich.console import Console
import os
import time
import re
import requests
import argparse

script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, "output")
os.makedirs(output_dir, exist_ok=True)
parser = argparse.ArgumentParser(description="SCRAPER7 Web Crawler")
parser.add_argument("-u", "--url", type=str, help="Path to .txt file containing list of websites (one per line)")
parser.set_defaults(contacts=True, txt=True)
contacts_group = parser.add_mutually_exclusive_group()
contacts_group.add_argument("-c","--contacts", dest="contacts", action="store_true", help="Enable contact extraction")
contacts_group.add_argument("-nc","--no-contacts", dest="contacts", action="store_false", help="Disable contact extraction")
txt_group = parser.add_mutually_exclusive_group()
txt_group.add_argument("-t","--txt", dest="txt", action="store_true", help="Enable TXT output")
txt_group.add_argument("-nt","--no-txt", dest="txt", action="store_false", help="Disable TXT output")
parser.add_argument("-d","--depth", type=int, default=2, help="Crawl depth level")
parser.add_argument("--pdf", action="store_true", default=False, help="Enable PDF download")
parser.add_argument("-ss","--screenshot", action="store_true", default=False, help="Enable screenshot saving")
main_domain_group = parser.add_mutually_exclusive_group()
main_domain_group.add_argument("-md", "--main-domain", dest="main_domain", action="store_true", help="Restrict to main domain")
main_domain_group.add_argument("-nmd","--no-main-domain", dest="main_domain", action="store_false", help="Allow crawling outside main domain")
parser.set_defaults(main_domain=False)
args = parser.parse_args()

scrape_depth = args.depth
enable_pdf_download = args.pdf
enable_screenshot_saving = args.screenshot
enable_contact_extraction = args.contacts
enable_txt_output = args.txt
restrict_to_main_domain = args.main_domain
social_domains = {"facebook.com", "instagram.com", "www.linkedin.com", "youtube.com", "twitter.com", "tiktok.com", "x.com"}

def download_pdf(url, save_dir):
    try:
        r = requests.get(url, timeout=10)
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

def extract_contacts(text):
    emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    names = re.findall(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', text)
    results = []
    for match in re.finditer(r'[\w\.-]+@[\w\.-]+\.\w+', text):
        email = match.group()
        start = max(0, match.start() - 200)
        end = min(len(text), match.end() + 200)
        context = text[start:end]
        phones = extract_phones(context)
        local = email.split("@")[0]
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

def get_safe_filename(url):
    return url.replace("https://", "").replace("http://", "").replace("/", "_").replace("?", "_").replace(":", "_")

def get_page_text_and_links(playwright, url, screenshot_dir=None):
    browser = None
    try:
        head = requests.head(url, timeout=10, allow_redirects=True)
        if head.status_code in [401, 403, 404, 500]:
            print(f"Skipping {url}: HTTP {head.status_code}")
            return "", set()

        browser = playwright.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        page = context.new_page()
        page.goto(url, timeout=15000)
        page.wait_for_load_state("domcontentloaded")
        if screenshot_dir and enable_screenshot_saving:
            filename = os.path.join(screenshot_dir, get_safe_filename(url) + ".png")
            page.screenshot(path=filename, full_page=True)
        text = page.inner_text("body")
        links, media_links = get_links_from_page(page, url)
        return text, links
    except Exception as e:
        print(f"Failed to scrape {url}: {e}")
        return "", set()
    finally:
        if browser:
            browser.close()

def scrape_with_depth(playwright, start_url, max_depth):
    global screenshots_dir
    global pdf_dir
    visited = set()
    text_data = []
    to_visit = [(start_url, 0)]
    main_domain = urlparse(start_url).netloc.replace("www.", "")
    screenshots_dir = os.path.join(output_dir, main_domain) if enable_screenshot_saving else None
    pdf_dir = os.path.join(output_dir, main_domain, "pdfs") if enable_pdf_download else None
    if screenshots_dir:
        os.makedirs(screenshots_dir, exist_ok=True)
    if pdf_dir:
        os.makedirs(pdf_dir, exist_ok=True)
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
            url for url, depth in current_level_tasks
            if url not in visited and not any(url.lower().endswith(ext) for ext in media_extensions)
        }
        total = len(unique_pending_links)
        count = 1
        for current_url, depth in current_level_tasks:
            if current_url in visited or depth > max_depth:
                continue
            start_time = time.time()
            text, links = get_page_text_and_links(playwright, current_url, screenshot_dir=screenshots_dir)
            if enable_pdf_download and current_url.lower().endswith(".pdf") and pdf_dir:
                download_pdf(current_url, pdf_dir)
            end_time = time.time()
            elapsed = end_time - start_time
            print(f"Scraping ({count}/{total}) [{elapsed:.2f}s]: {current_url}")
            count += 1
            text_data.append([current_url, text])
            visited.add(current_url)
            if depth < max_depth:
                for link in links:
                    link_domain = urlparse(link).netloc.replace("www.", "")
                    if link not in visited and not any(link.lower().endswith(ext) for ext in media_extensions):
                        if not restrict_to_main_domain or link_domain == main_domain or depth == 0:
                            next_depth = depth + 1 if link_domain not in social_domains else max_depth + 1
                            to_visit.append((link, next_depth))
    return text_data

def print_config():
    fig = Figlet(font='slant')
    console = Console()
    console.print(fig.renderText('SCRAPER6.5'), style="bold green")
    config_items = [
        ("Depth", scrape_depth),
        ("Contacts", enable_contact_extraction and enable_txt_output),
        ("Screenshot", enable_screenshot_saving),
        ("Download PDF", enable_pdf_download),
        ("Main domain", restrict_to_main_domain)
    ]

    label_width = max(len(label) for label, _ in config_items)
    for label, value in config_items:
        print(f"{label.ljust(label_width)} --- {value}")


if __name__ == "__main__":
    print_config()
    urls = []
    if args.url:
        try:
            with open(args.url, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"Failed to read URL file: {e}")
            exit(1)
    else:
        website = input("website: ").strip()
        urls = [website]

    with sync_playwright() as playwright:
        for website in urls:
            print(f"Starting scrape for: {website}")
            scraped_data = scrape_with_depth(playwright, website, scrape_depth)
            if enable_contact_extraction and enable_txt_output:
                domain_part = urlparse(website).netloc.replace("www.", "").replace(".", "_")
                contact_file = os.path.join(output_dir, f"contacts_{domain_part}.txt")
                seen_emails = set()
                seen_phones = set()
                with open(contact_file, "w", encoding="utf-8") as contact_out:
                    for url, text in scraped_data:
                        name_email_pairs = extract_contacts(text)
                        for name, email, phones in name_email_pairs:
                            unique_phones = [p for p in phones if p not in seen_phones]
                            if email not in seen_emails and unique_phones:
                                contact_out.write(f"{name}${email}${'$'.join(unique_phones)}\n")
                                seen_emails.add(email)
                                seen_phones.update(unique_phones)
                print(f"Contacts saved to {contact_file}")
    print("Complete.")