try:
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ModuleNotFoundError:
    print("webdriver_manager or selenium module not found. Please install them using 'pip install webdriver-manager selenium'")
    exit()

from bs4 import BeautifulSoup as bs
import time

def init_browser():
    service = ChromeService(executable_path=ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.headless = False
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    return webdriver.Chrome(service=service, options=options)

def scrape_info():
    browser = init_browser()
    
    # Updated URL for Mars news
    url = "https://science.nasa.gov/mars/stories/"
    
    try:
        browser.get(url)
        
        # Wait for the content to load
        time.sleep(2)
        
        html = browser.page_source
        soup = bs(html, "html.parser")
        
        # Find the first news article in the list
        article = soup.find("div", class_="hds-content-item")
        
        if article:
            # Extract the title and paragraph
            title_element = article.find("div", class_="hds-a11y-heading-22")
            paragraph_element = article.find("p", class_="margin-top-0 margin-bottom-1")
            
            if title_element and paragraph_element:
                results_title = title_element.text.strip()
                results_paragraph = paragraph_element.text.strip()
            else:
                results_title = "No title found"
                results_paragraph = "No content found"
        else:
            results_title = "No articles found"
            results_paragraph = "Could not retrieve Mars news content"
        
        news_data = {
            "title": results_title,
            "paragraph": results_paragraph
        }
        
        return news_data
    except Exception as e:
        print(f"Error during scraping: {e}")
        return {
            "title": "Error retrieving data",
            "paragraph": f"An error occurred: {str(e)}"
        }
    finally:
        browser.quit()