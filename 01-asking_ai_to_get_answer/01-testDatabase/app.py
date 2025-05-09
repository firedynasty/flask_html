from flask import Flask, render_template, jsonify
import sqlite3

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/bible-data')
def get_bible_data():
    conn = sqlite3.connect('test.db')
    c = conn.cursor()
    c.execute("SELECT set_key, slides_data FROM bible_interpretation")
    data = [{"set_key": row[0], "slides_data": row[1]} 
            for row in c.fetchall()]
    conn.close()
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True)