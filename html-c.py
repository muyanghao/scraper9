from playwright.sync_api import sync_playwright
import requests
import time

def fetch_html(url, output_file="page.html", use_browser=True):
    if use_browser:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
            page = context.new_page()

            print(f"[INFO] Opening {url} with browser...")
            page.goto(url, timeout=60000)
            time.sleep(1)
            html = page.content()

            browser.close()
    else:
        print(f"[INFO] Fetching {url} using requests...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        html = response.text

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[DONE] HTML saved to {output_file}")

if __name__ == "__main__":
    target_url = input("Enter the URL: ").strip()
    mode = input("Use browser? (y/n): ").strip().lower()
    use_browser = mode == "y"
    fetch_html(target_url, use_browser=use_browser)
