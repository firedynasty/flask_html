# Mars Data Web Application

## Overview
This web application scrapes the latest news from NASA's Mars mission website and displays it along with Mars facts and hemisphere images in an interactive format. The application uses Flask as the web framework and MongoDB to store the scraped data.

## Features
- Scrapes the latest Mars news headlines and summaries from NASA's website
- Displays Mars facts and comparison with Earth
- Showcases Mars hemisphere images in an interactive carousel/slideshow
- Provides links to more Mars stories

## Getting Started

### Prerequisites
Make sure you have Python 3.6+ installed on your system. You'll also need MongoDB installed and running locally.

### Installation

1. Clone this repository or download the source code.

2. Create a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows, use: venv\Scripts\activate
   ```

3. Install the required dependencies:
   ```bash
   pip install flask flask-pymongo pymongo selenium beautifulsoup4 webdriver-manager requests
   ```

4. Make sure you have Chrome installed (required for the web scraping)

### Project Structure
```
mission_to_mars/
├── app.py                 # Flask application
├── scrape_news.py         # Web scraping script
├── static/                # Static assets
│   └── images/            # Mars hemisphere images
│       ├── image1.jpg
│       ├── image2.jpg
│       ├── image3.jpg
│       └── image4.jpg
└── templates/             # HTML templates
    └── index.html         # Main page
```

### Running the Application

1. Make sure MongoDB is running on your system.

2. Run the Flask application:
   ```bash
   python app.py
   ```

3. Open your web browser and navigate to:
   ```
   http://127.0.0.1:5001/
   ```

4. Click the "Get the news!" button to scrape the latest Mars news data.

## How It Works

1. The Flask application serves the main page with any previously stored data.
2. When the user clicks "Get the news!" button, the app runs the scraping function.
3. The scraping function uses Selenium and BeautifulSoup to extract the latest Mars news from NASA's website.
4. The scraped data is stored in MongoDB.
5. The page refreshes, displaying the newly scraped information.
6. Mars hemisphere images are displayed in a carousel that rotates automatically.

## Customization

### Images
To use your own Mars hemisphere images:
1. Place your images in the `static/images/` folder
2. Name them `image1.jpg`, `image2.jpg`, `image3.jpg`, and `image4.jpg`
3. Alternatively, update the image paths in `index.html` to match your image filenames

### MongoDB Connection
By default, the application connects to MongoDB running on localhost. If you need to connect to a different MongoDB instance, modify the `MONGO_URI` in `app.py`.

## Troubleshooting

### Images Not Loading
If your images are not loading:
1. Verify that your images are placed in the `static/images/` directory
2. Check the browser console for 404 errors
3. Ensure that the file names in the HTML match the actual file names

### Scraping Issues
If the scraping function fails:
1. Check if the NASA website structure has changed
2. Verify that you have Chrome installed and the webdriver is correctly configured
3. Check the error message in the terminal where Flask is running

## Dependencies
- Flask: Web framework
- Flask-PyMongo: MongoDB integration for Flask
- PyMongo: MongoDB driver for Python
- Selenium: Web browser automation for scraping
- BeautifulSoup4: HTML parsing
- Webdriver-Manager: Chrome webdriver management
- Requests: HTTP library

## License
This project is open source and available for anyone to use and modify.

## Acknowledgments
- NASA for providing the Mars data
- Bootstrap for the front-end components
