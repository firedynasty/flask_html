from flask import Flask, render_template, jsonify
import sqlite3

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/sets')
def get_sets():
    conn = sqlite3.connect('test.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT set_key FROM bible_interpretation ORDER BY set_key")
    sets = [row[0] for row in c.fetchall()]
    conn.close()
    return jsonify(sets)

@app.route('/api/interpretation/<set_key>')
def get_interpretation(set_key):
    conn = sqlite3.connect('test.db')
    c = conn.cursor()
    c.execute("SELECT slides_data FROM bible_interpretation WHERE set_key = ?", (set_key,))
    result = c.fetchone()
    conn.close()
    
    if result:
        return jsonify({"slides_data": result[0]})
    return jsonify({"error": "Set not found"}), 404

if __name__ == '__main__':
    app.run(debug=True)