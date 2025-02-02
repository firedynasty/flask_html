from flask import Flask, render_template, jsonify
import sqlite3

app = Flask(__name__)

@app.route('/')
def index():
    conn = sqlite3.connect('chineseFlashcards.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT set_name FROM chinese")
    set_names = [row[0] for row in c.fetchall()]
    conn.close()
    return render_template('index.html', set_names=set_names)

@app.route('/api/flashcards-data')
def get_bible_data():
    conn = sqlite3.connect('chineseFlashcards.db')
    c = conn.cursor()
    c.execute("SELECT set_name, json_value FROM chinese")
    data = [{"set_key": row[0], "slides_data": row[1]} 
            for row in c.fetchall()]
    conn.close()
    return jsonify(data)

@app.route('/api/set-data/<set_name>')
def get_set_data(set_name):
    conn = sqlite3.connect('chineseFlashcards.db')
    c = conn.cursor()
    c.execute("SELECT json_value FROM chinese WHERE set_name = ?", (set_name,))
    result = c.fetchone()
    conn.close()
    if result:
        return jsonify({"slides_data": result[0]})
    return jsonify({"error": "Set not found"}), 404

if __name__ == '__main__':
    app.run(debug=True)
