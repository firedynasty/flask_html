import argparse
import requests
from bs4 import BeautifulSoup
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import json

def init_browser(headless=True):
    """Initialize and return a Chrome browser instance"""
    options = Options()
    if headless:
        options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    browser = webdriver.Chrome(service=service, options=options)
    return browser

def scrape_verse_content(browser, verse_url):
    """Scrape the content of a specific verse"""
    try:
        browser.get(verse_url)
        time.sleep(2)
        
        # Wait for verse content to load
        wait = WebDriverWait(browser, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "p")))
        
        html = browser.page_source
        soup = BeautifulSoup(html, "html.parser")
        
        # Look for verse content (this selector might need adjustment based on actual HTML structure)
        verse_content_element = soup.find("span", class_=re.compile(r"verse-content|verse-text"))
        
        if not verse_content_element:
            # Try alternative selectors if the first one doesn't work
            verse_content_element = soup.find("div", class_=re.compile(r"verse|bible-text"))
            
        if verse_content_element:
            return verse_content_element.get_text().strip()
        else:
            return "Verse content not found"
            
    except Exception as e:
        print(f"Error scraping verse content: {e}")
        return "Error fetching content"

def scrape_bible_verses(url, fetch_content=False):
    """
    Scrape popular Bible verses from the given URL
    
    Args:
        url (str): The URL of the Bible.com page to scrape
        fetch_content (bool): Whether to also fetch the verse content
        
    Returns:
        list: A list of dictionaries containing verse information
    """
    browser = init_browser()
    
    try:
        print(f"Accessing {url}...")
        browser.get(url)
        
        # Wait for the page to load completely
        time.sleep(3)
        
        # Use WebDriverWait to ensure the content is loaded
        wait = WebDriverWait(browser, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "a")))
        
        # Get the page source and parse it with BeautifulSoup
        html = browser.page_source
        soup = BeautifulSoup(html, "html.parser")
        
        # Look for verse links - pattern from the example: <a class="no-underline text-gray-50" href="/bible/111/PSA.33.20">
        verse_links = soup.find_all("a", class_="no-underline", href=re.compile(r"/bible/\d+/"))
        
        if not verse_links:
            print("No verse links found with the expected pattern. Trying alternative patterns...")
            
            # Try alternative patterns for verse links
            verse_links = soup.find_all("a", href=re.compile(r"/bible/\d+/"))
        
        print(f"Found {len(verse_links)} verses")
        
        # Extract verses information
        verses = []
        for link in verse_links:
            # Find the verse text which might be in a paragraph tag
            verse_text_element = link.find("p") or link
            verse_text = verse_text_element.get_text().strip()
            
            # Get the href attribute
            href = link.get("href")
            full_url = f"https://www.bible.com{href}" if href and href.startswith("/") else href
            
            verse_info = {
                "reference": verse_text,
                "url": full_url
            }
            
            # Optionally fetch the verse content
            if fetch_content and full_url:
                print(f"Fetching content for {verse_text}...")
                verse_info["content"] = scrape_verse_content(browser, full_url)
            
            verses.append(verse_info)
        
        return verses
        
    except Exception as e:
        print(f"Error during scraping: {e}")
        return []
    finally:
        browser.quit()

def main():
    """Main function to run the script from command line"""
    parser = argparse.ArgumentParser(description="Scrape Bible verses from a given URL")
    parser.add_argument("url", help="URL of the Bible.com page to scrape")
    parser.add_argument("--content", action="store_true", help="Also fetch verse content")
    parser.add_argument("--output", help="Output JSON file to save results")
    args = parser.parse_args()
    
    verses = scrape_bible_verses(args.url, fetch_content=args.content)
    
    if verses:
        print("\nPopular Bible Verses:")
        print("====================")
        for i, verse in enumerate(verses, 1):
            print(f"{i}. {verse['reference']}")
            print(f"   Link: {verse['url']}")
            if args.content and "content" in verse:
                print(f"   Content: {verse['content']}")
            print()
            
        # Save to JSON file if specified
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(verses, f, ensure_ascii=False, indent=4)
            print(f"Results saved to {args.output}")
    else:
        print("No verses found or there was an error during scraping.")

if __name__ == "__main__":
    main()
