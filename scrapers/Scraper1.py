from playwright.sync_api import sync_playwright
from urllib.parse import urljoin
import time


def get_links_from_page(page, base_url):
    raw_links = page.eval_on_selector_all("a[href]", "elements => elements.map(el => el.href)")
    clean_links = set()
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.tiff', '.ico'}

    for link in raw_links:
        absolute = urljoin(base_url, link)
        
        if any(absolute.endswith(ext) for ext in image_extensions):
            continue

        if absolute.startswith("http"):
            clean_links.add(absolute)
    
    return clean_links



def get_page_text_and_links(playwright, url):
    browser = None
    try:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1"
            }
        )
        page = context.new_page()
        page.goto(url, timeout=60000)
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        text = page.inner_text("body")
        links = get_links_from_page(page, url)
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
    current_depth = -1

    while to_visit:
        depth_level = to_visit[0][1]
        same_level_links = [item for item in to_visit if item[1] == depth_level]

        if depth_level != current_depth:
            current_depth = depth_level
            print(f"\ndepth {current_depth}\n")

        total = len(same_level_links)
        count = 1

        for i in range(len(to_visit)):
            current_url, depth = to_visit.pop(0)
            if depth != current_depth or current_url in visited or depth > max_depth:
                continue

            print(f"Scraping ({count}/{total}): {current_url}")
            text, links = get_page_text_and_links(playwright, current_url)
            text_data.append([current_url, text])
            visited.add(current_url)
            count += 1

            if depth < max_depth:
                for link in links:
                    if link not in visited:
                        to_visit.append((link, depth + 1))

            time.sleep(0.5)

    return text_data


if __name__ == "__main__":

    website = "https://google.com/"       #url
    scrape_depth = 1               

    with sync_playwright() as playwright:
        scraped_data = scrape_with_depth(playwright, website, scrape_depth)

    output_file = "scraped_text.txt"

    with open(output_file, "a", encoding="utf-8") as file:  
        for url, text in scraped_data:
            file.write(f"URL: {url}\n")
            file.write("Text:\n")
            file.write(text.replace("\n", " ") + "\n")
            file.write("=" * 80 + "\n\n")  
    
    print("complete.")

