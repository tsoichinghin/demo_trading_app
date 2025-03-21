import tempfile
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
from .config import logger
import re
import shutil

def fetch_announcement_urls(CURRENT_DATE):
    """從公告列表頁提取標題和 URL"""
    url = "https://www.binance.com/en/support/announcement/list/161"
    options = Options()
    options.add_argument("--headless")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,720")
    temp_dir = tempfile.mkdtemp()
    options.add_argument(f"--user-data-dir={temp_dir}")
    driver = webdriver.Chrome(options=options)
    driver.get(url)
    
    try:
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/en/support/announcement/detail/']"))
        )
        html = driver.page_source
    except Exception as e:
        logger.error(f"列表頁加載失敗：{e}")
        driver.quit()
        shutil.rmtree(temp_dir, ignore_errors=True)
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    announcements = []
    
    for link in soup.select("a[href*='/en/support/announcement/detail/']"):
        title = link.get_text(strip=True)
        href = link.get("href")
        if title.startswith("Notice of Removal of Spot Trading Pairs -"):
            date_str = title.split(" - ")[-1]
            try:
                ann_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                if ann_date >= CURRENT_DATE:
                    full_url = f"https://www.binance.com{href}" if href.startswith("/en") else href
                    announcements.append({"title": title, "url": full_url, "date": ann_date})
            except ValueError:
                logger.warning(f"無法解析日期：{date_str}")
    
    driver.quit()
    shutil.rmtree(temp_dir, ignore_errors=True)
    return announcements

def fetch_delisting_pairs(announcement_url):
    """從單個公告頁面提取交易對"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,720")
    temp_dir = tempfile.mkdtemp()
    options.add_argument(f"--user-data-dir={temp_dir}")
    driver = webdriver.Chrome(options=options)
    driver.get(announcement_url)
    
    try:
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.ID, "support_article"))
        )
        html = driver.page_source
    except Exception as e:
        logger.error(f"頁面加載失敗（{announcement_url}）：{e}")
        driver.quit()
        shutil.rmtree(temp_dir, ignore_errors=True)
        return set()
    
    driver.quit()
    shutil.rmtree(temp_dir, ignore_errors=True)
    soup = BeautifulSoup(html, 'html.parser')
    delisting_pairs = set()
    pattern = r"At\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s*\(UTC\)\s*[:\s]*([\w/]+(?:,\s*[\w/]+)*)"
    
    article = soup.find("div", id="support_article")
    if article:
        article_text = " ".join(article.stripped_strings)
        match = re.search(pattern, article_text)
        if match:
            pairs = match.group(1).split(", ")
            delisting_pairs.update([pair.strip() for pair in pairs])
    
    if not delisting_pairs:
        meta_desc = soup.find("meta", {"name": "description"})
        if meta_desc and meta_desc.get("content"):
            content = meta_desc["content"]
            match = re.search(pattern, content)
            if match:
                pairs = match.group(1).split(", ")
                delisting_pairs.update([pair.strip() for pair in pairs])
    
    return delisting_pairs

def scan_markets(CURRENT_DATE):
    """掃描市場並檢測即將關閉的交易對"""
    announcements = fetch_announcement_urls(CURRENT_DATE)
    all_delisting_pairs = set()
    
    for ann in announcements:
        delisting_pairs = fetch_delisting_pairs(ann["url"])
        all_delisting_pairs.update(delisting_pairs)
    
    return all_delisting_pairs
