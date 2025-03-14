# Bible Verse Scraper

A Python tool for scraping Bible verses from Bible.com pages.

## Overview

This tool allows you to extract Bible verse references, links, and optional verse content from Bible.com pages. It's useful for collecting popular verses, studying specific chapters, or creating your own verse collections.

## Features

- Extract verse references and their URLs from Bible.com pages
- Scrape actual verse content when requested
- Filter duplicates for cleaner results
- Export results to JSON for further processing
- Headless browser operation by default (runs in background)

## Installation

### Prerequisites

- Python 3.6+
- Chrome browser installed

### Setup

1. Clone this repository or download the script file
2. Install the required dependencies:

```bash
pip install requests beautifulsoup4 selenium webdriver-manager
```

## Usage

### Basic Usage

To scrape verse references from a Bible.com page:

```bash
python bible-verse-scraper.py https://www.bible.com/bible-verses/111/PSA.33.NIV
```

### Advanced Usage

To also fetch the verse content and save results to a JSON file:

```bash
python bible-verse-scraper.py https://www.bible.com/bible-verses/111/PSA.33.NIV --content --output verses.json
```

### Command Line Arguments

- `url`: The Bible.com URL to scrape (required)
- `--content`: Also fetch the actual verse content (optional)
- `--output`: Specify a JSON file to save the results (optional)

## Example Output

```
Accessing https://www.bible.com/bible-verses/111/PSA.33.NIV...
Found 5 verses

Popular Bible Verses:
====================
1. Psalms 33:20
   Link: https://www.bible.com/bible/111/PSA.33.20
   Content: We wait in hope for the LORD; he is our help and our shield.

2. Explore Psalms 33:20
   Link: https://www.bible.com/bible/111/PSA.33.20
   Content: We wait in hope for the LORD; he is our help and our shield.

3. Psalms 33:18-19
   Link: https://www.bible.com/bible/111/PSA.33.18-19
   Content: But the eyes of the LORD are on those who fear him, on those whose hope is in his unfailing love, to deliver them from death and keep them alive in famine.

...
```

## How It Works

1. The script initializes a headless Chrome browser using Selenium WebDriver
2. It navigates to the provided URL and waits for the page to load
3. Using BeautifulSoup, it parses the HTML to find verse links matching specific patterns
4. For each link, it extracts the verse reference and its URL
5. If requested, it navigates to each verse's page to scrape the actual content
6. Results are displayed in a readable format and optionally saved to a JSON file

## Troubleshooting

- **No verses found**: Try visiting the URL manually to verify there are Bible verses on the page
- **Slow performance**: Consider setting `headless=False` in the `init_browser` function to see what's happening
- **Content not found**: The HTML structure of Bible.com might change; adjust the selectors in `scrape_verse_content`

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool is for personal, educational, or research purposes only. Please respect Bible.com's terms of service and do not use this for scraping large amounts of data
