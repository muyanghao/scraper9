import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
import csv
import numpy

def extract_visible_text(soup):
    for unwanted in soup(['style', 'script', 'header', 'footer', 'nav', 'aside', 'form']):
        unwanted.decompose()
    text = soup.get_text(separator=' ', strip=True)
    text = re.sub(r'\s+', ' ', text)
    return text

def scrape_page(url, base_domain, visited, text_data, max_pages):
    if len(visited) >= max_pages:
        return
    if url in visited:
        return
    try:
        response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'})
        if response.status_code != 200:
            return
        visited.add(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        text = extract_visible_text(soup)
        text_data.append([url, text])
        for link_tag in soup.find_all('a', href=True):
            href = link_tag['href']
            full_url = urljoin(url, href)
            parsed_url = urlparse(full_url)

            if parsed_url.netloc != base_domain:   
                continue                            
            clean_url = parsed_url.scheme + "://" + parsed_url.netloc + parsed_url.path
            if clean_url not in visited:
                scrape_page(clean_url, base_domain, visited, text_data, max_pages)
    except:
        return

if __name__ == "__main__":
    website = input("Enter URL ")
    parsed_base = urlparse(website)
    base_domain = parsed_base.netloc
    visited = set()
    text_data = []
    max_pages = 10   #Adjust the maximum 
    scrape_page(website, base_domain, visited, text_data, max_pages)
    with open("scraped_text.csv", "w", encoding="utf-8", newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["URL", "Text"])
        writer.writerows(text_data)
    print("complete")