# import necessary libraries
from flask import Flask, render_template, redirect
from flask_pymongo import PyMongo
import scrape_news

# create instance of Flask app
app = Flask(__name__)

# Configure MongoDB connection
# Ensure MongoDB is running on localhost:27017
app.config["MONGO_URI"] = "mongodb://localhost:27017/mars_db"
mongo = PyMongo(app)

# Define image URLs and organize them into a matrix
image_url = {'url': 'https://www.jpl.nasa.gov/spaceimages/images/mediumsize/PIA18182_ip.jpg'}

image_files = [
    {'title': 'Valles Marineris', 'img_url': 'https://astropedia.astrogeology.usgs.gov/download/Mars/Viking/valles_marineris_enhanced.tif/full.jpg'},
    {'title': 'Cerberus Hemisphere', 'img_url': 'https://astropedia.astrogeology.usgs.gov/download/Mars/Viking/cerberus_enhanced.tif/full.jpg'},
    {'title': 'Schiaparelli Hemisphere', 'img_url': 'https://astropedia.astrogeology.usgs.gov/download/Mars/Viking/schiaparelli_enhanced.tif/full.jpg'},
    {'title': 'Syrtis Major', 'img_url': 'https://astropedia.astrogeology.usgs.gov/download/Mars/Viking/syrtis_major_enhanced.tif/full.jpg'}
]

image_matrix = []
count1 = 0
for i in range(int(len(image_files) / 2)):
    image_matrix.append([])
    image_matrix[i].append(image_files[count1])
    image_matrix[i].append(image_files[count1 + 1])
    count1 += 2

# create route that renders index.html template
@app.route("/")
def home():
    news_info = mongo.db.mars_data.find_one()
    return render_template("index.html", image_url=image_url, news_info=news_info)

# create route that triggers scraping and updates the database
@app.route("/scrape")
def scrape():
    news_data = scrape_news.scrape_info()
    # Update with the correct PyMongo syntax for your version
    mongo.db.mars_data.update_one({}, {"$set": news_data}, upsert=True)
    return redirect("/")

# create route that renders images.html template
@app.route("/images")
def second_page_images():
    return render_template("images.html", list=image_matrix)

# run the Flask app
if __name__ == "__main__":
    app.run(debug=True, port=5001)



