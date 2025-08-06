import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re
import time

# === 加载城市网址列表 ===
with open("urls0.txt", "r", encoding="utf-8") as f:
    urls = [line.strip() for line in f if line.strip()]

# === 正则表达式 ===
email_pattern = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z.]+")
phone_pattern = re.compile(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
name_pattern = re.compile(r"(?:Mayor|Reeve)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)")

# === 抓取函数 ===
def extract_contact_info(url):
    try:
        res = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.text, "html.parser")
        text_blocks = soup.find_all(["p", "div", "li", "td", "section", "span", "a"])
        for block in text_blocks:
            text = block.get_text(separator=" ", strip=True)
            if "mayor" in text.lower() or "reeve" in text.lower():
                name_match = name_pattern.search(text)
                email_match = email_pattern.search(text)
                phone_match = phone_pattern.search(text)

                name = name_match.group(1) if name_match else "N/A"
                email = email_match.group(0) if email_match else "N/A"
                phone = phone_match.group(0) if phone_match else "N/A"

                return name, email, phone
        return "N/A", "N/A", "N/A"
    except:
        return "N/A", "N/A", "N/A"

# === 处理所有城市 ===
output_lines = []
for i, url in enumerate(urls):
    city = urlparse(url).netloc.split(".")[0].capitalize()
    name, email, phone = extract_contact_info(url)
    output_lines.append(f"{city}${name}${email}${phone}")
    print(f"[{i+1}/{len(urls)}] {city} ✅")

    time.sleep(1)  # 防止封锁

# === 写入输出文件 ===
with open("mayor_contacts.txt", "w", encoding="utf-8") as f:
    for line in output_lines:
        f.write(line + "\n")

print("\n✅ 所有城市处理完毕，结果已保存到 mayor_contacts.txt")
