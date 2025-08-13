from playwright.sync_api import sync_playwright
from urllib.parse import urljoin, urlparse
import os
import time
import re

script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, "output")
os.makedirs(output_dir, exist_ok=True)

enable_contact_extraction = True
restrict_to_main_domain = False

def extract_contacts(text):
    emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    names = re.findall(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', text)
    unique = {}
    for email in set(emails):
        local = email.split("@")[0]
        match_name = next((n for n in names if local.lower() in n.lower().replace(" ", "")), None)
        name = match_name or "Unknown"
        if email not in unique:
            unique[email] = name
    return [(name, email) for email, name in unique.items()]

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
                        if not restrict_to_main_domain or link_domain == main_domain or depth == 0:
                            to_visit.append((link, depth + 1))

    return text_data

if __name__ == "__main__":
    scrape_depth = 2
    print ("Depth:",scrape_depth)
    print ("Main domain?",restrict_to_main_domain)
    website = input("website:")     
    

    with sync_playwright() as playwright:
        scraped_data = scrape_with_depth(playwright, website, scrape_depth)

    if enable_contact_extraction:
        domain_part = urlparse(website).netloc.replace("www.", "").replace(".", "_")
        contact_file = os.path.join(output_dir, f"contacts_{domain_part}.txt")
        seen_emails = set()
        with open(contact_file, "w", encoding="utf-8") as contact_out:
            for url, text in scraped_data:
                name_email_pairs = extract_contacts(text)
                for name, email in name_email_pairs:
                    if email not in seen_emails:
                        contact_out.write(f"{name} - {email}\n")
                        seen_emails.add(email)
        print(f"Contacts saved to {contact_file}")

    print("Complete.")
