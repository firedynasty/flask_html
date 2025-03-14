import os
from flask import Flask, render_template, jsonify
import sqlite3

# Get the absolute path of the directory containing application.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
           template_folder=os.path.join(BASE_DIR, 'templates'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/sets')
def get_sets():
    db_path = os.path.join(BASE_DIR, 'test.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT DISTINCT set_key FROM bible_interpretation ORDER BY set_key")
    sets = [row[0] for row in c.fetchall()]
    conn.close()
    return jsonify(sets)

@app.route('/api/interpretation/<set_key>')
def get_interpretation(set_key):
    db_path = os.path.join(BASE_DIR, 'test.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT slides_data FROM bible_interpretation WHERE set_key = ?", (set_key,))
    result = c.fetchone()
    conn.close()

    if result:
        return jsonify({"slides_data": result[0]})
    return jsonify({"error": "Set not found"}), 404