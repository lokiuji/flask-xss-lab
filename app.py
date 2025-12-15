import os
import time
import sqlite3
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, session, make_response, jsonify

app = Flask(__name__)
app.secret_key = 'super_secret_key'

app.config['SESSION_COOKIE_HTTPONLY'] = False 
app.config['SESSION_COOKIE_SECURE'] = False

@app.after_request
def add_header(response):
    response.headers['X-XSS-Protection'] = '0'
    return response

LAST_DB_RESET = time.time()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
DB_PATH = os.path.join(BASE_DIR, 'xss_lab.db')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
SAFE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt'} 

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- ПРЕСЕТИ ---
PRESET_FILES = {
    'test_alert.html': '<script>alert("XSS Successful!")</script><h1>HACKED</h1>',
    'cookie_stealer.html': '<script>alert("VICTIM COOKIES:\\n" + document.cookie);</script>',
    'calc.exe': 'FAKE BINARY CONTENT',
}

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT DEFAULT 'user');''')
    cur.execute('''CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL);''')
    cur.execute('''CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL, upload_type TEXT NOT NULL, is_sanitized BOOLEAN DEFAULT 0);''')
    
    cur.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cur.fetchone():
        cur.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin', 'admin')")
    conn.commit()
    conn.close()

init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in SAFE_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'error', 'message': 'Login required'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- ROUTES ---

@app.route('/uploads/<name>')
def download_file(name):
    return send_from_directory(app.config['UPLOAD_FOLDER'], name)

@app.route('/check_db_version')
def check_db_version():
    return jsonify({'version': LAST_DB_RESET})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection(); cur = conn.cursor()
        try:
            cur.execute(f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'")
            user = cur.fetchone()
            if user:
                session['user_id'] = user['id']; session['username'] = user['username']; session['role'] = user['role']
                resp = make_response(redirect(url_for('dashboard')))
                resp.set_cookie('secret_bank_account', '1000000_USD', httponly=False)
                return resp
            else: flash('Invalid credentials', 'danger')
        except Exception as e: flash(f'SQL Error: {e}', 'danger')
        conn.close()
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        content = request.form['content']
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute('INSERT INTO comments (content) VALUES (?)', (content,))
        conn.commit(); conn.close()
        return jsonify({'status': 'success', 'message': 'Payload Saved!'})
    return render_template('xss.html', preset_files=PRESET_FILES.keys())

# === НОВІ МАРШРУТИ (STEP 1) ===

@app.route('/advanced')
@login_required
def advanced():
    return render_template('advanced.html')

# BLIND SQL ENDPOINT
@app.route('/api/check_username', methods=['POST'])
@login_required
def check_username():
    username = request.form.get('username', '')
    conn = get_db_connection()
    cur = conn.cursor()
    exists = False
    try:
        # Вразливий запит, але ми не повертаємо помилку!
        # Тільки True або False
        query = f"SELECT * FROM users WHERE username = '{username}'"
        cur.execute(query)
        if cur.fetchone():
            exists = True
    except:
        # При помилці SQL ми просто кажемо "не знайдено" (Blind Behavior)
        exists = False
        
    conn.close()
    return jsonify({'exists': exists})

# === OLD ROUTES ===

@app.route('/sqli', methods=['GET', 'POST'])
@login_required
def sqli():
    vuln_result, vuln_error, vuln_query = None, None, ""
    sec_result, sec_query = None, ""
    search_term = ""
    if request.method == 'POST':
        search_term = request.form.get('search', '')
        if search_term:
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                vuln_query = f"SELECT id, username, role FROM users WHERE username LIKE '%{search_term}%'"
                cur.execute(vuln_query)
                vuln_result = cur.fetchall()
            except Exception as e: vuln_error = str(e)
            try:
                cur = conn.cursor()
                cur.execute("SELECT id, username, role FROM users WHERE username LIKE ?", (f'%{search_term}%',))
                sec_result = cur.fetchall()
            except: pass
            conn.close()
    return render_template('sqli.html', search_term=search_term, vuln_result=vuln_result, vuln_error=vuln_error, vuln_query=vuln_query, sec_result=sec_result, sec_query=sec_query)

@app.route('/stealth')
@login_required
def stealth():
    return render_template('stealth.html')

@app.route('/scan_file', methods=['POST'])
@login_required
def scan_file():
    file = request.files.get('file')
    if not file: return jsonify({'status':'error', 'message':'No file'})
    content = file.read().lower()
    VIRUS_SIGNATURES = [b'script', b'alert', b'prompt', b'onerror', b'onload', b'eval', b'javascript']
    detected = [s.decode() for s in VIRUS_SIGNATURES if s in content]
    if detected: return jsonify({'status':'blocked', 'message':f'⛔ BLOCKED: {", ".join(detected)}'})
    return jsonify({'status':'clean', 'message':'✅ CLEAN'})

@app.route('/upload_vulnerable', methods=['POST'])
@login_required
def upload_vulnerable():
    file = request.files.get('file')
    if not file: return jsonify({'status':'error', 'message':'No file'})
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], file.filename))
    save_file_to_db(file.filename, 'vulnerable', False)
    return jsonify({'status':'warning', 'message':f'💀 {file.filename} Executed!'})

@app.route('/upload_secure', methods=['POST'])
@login_required
def upload_secure():
    file = request.files.get('file')
    if not file: return jsonify({'status':'error', 'message':'No file'})
    filename = file.filename
    is_sanitized = False
    if not allowed_file(filename):
        filename = filename + ".txt"
        is_sanitized = True
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    save_file_to_db(filename, 'secure', is_sanitized)
    if is_sanitized:
        return jsonify({'status':'success', 'message':f'🛡️ Sanitized: {filename}'})
    return jsonify({'status':'success', 'message':f'✅ Uploaded: {filename}'})

@app.route('/upload_preset', methods=['POST'])
@login_required
def upload_preset():
    fname = request.form.get('filename')
    mode = request.form.get('mode')
    if fname not in PRESET_FILES: return jsonify({'status':'error'})
    content = PRESET_FILES[fname]
    is_sanitized = False
    if mode == 'secure':
        if not allowed_file(fname):
            fname = fname + ".txt"
            is_sanitized = True
    with open(os.path.join(app.config['UPLOAD_FOLDER'], fname), 'w', encoding='utf-8') as f: 
        f.write(content)
    save_file_to_db(fname, mode, is_sanitized)
    return jsonify({'status':'success', 'message':f'Injected: {fname}'})

@app.route('/inject_all', methods=['POST'])
@login_required
def inject_all():
    for f, c in PRESET_FILES.items():
        with open(os.path.join(app.config['UPLOAD_FOLDER'], f), 'w', encoding='utf-8') as file: 
            file.write(c)
        save_file_to_db(f, 'vulnerable', False)
    return jsonify({'status':'warning', 'message':'ALL VIRUSES INJECTED'})

@app.route('/reset_db', methods=['POST'])
@login_required
def reset_db():
    global LAST_DB_RESET
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute('DELETE FROM comments;')
        cur.execute('DELETE FROM files;')
        cur.execute("DELETE FROM sqlite_sequence WHERE name='comments';")
        cur.execute("DELETE FROM sqlite_sequence WHERE name='files';")
        conn.commit()
    except: conn.rollback()
    conn.close()
    for f in os.listdir(UPLOAD_FOLDER):
        fp = os.path.join(UPLOAD_FOLDER, f)
        if os.path.isfile(fp): os.remove(fp)
    LAST_DB_RESET = time.time()
    return jsonify({'status':'info', 'message':'DB Cleared'})

def save_file_to_db(name, type, sanitized):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('INSERT INTO files (filename, upload_type, is_sanitized) VALUES (?, ?, ?)', (name, type, 1 if sanitized else 0))
    conn.commit(); conn.close()

@app.route('/vulnerable')
def win_vuln():
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT content FROM comments ORDER BY id DESC'); comms = cur.fetchall()
    cur.execute("SELECT filename FROM files WHERE upload_type='vulnerable' ORDER BY id DESC LIMIT 1"); 
    last_file = cur.fetchone()
    last_filename = last_file['filename'] if last_file else None
    conn.close()
    return render_template('vulnerable.html', comments=comms, last_file=last_filename)

@app.route('/secure')
def win_sec():
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT content FROM comments ORDER BY id DESC'); comms = cur.fetchall()
    cur.execute("SELECT filename, is_sanitized FROM files WHERE upload_type='secure' ORDER BY id DESC LIMIT 1"); 
    last_file_row = cur.fetchone()
    last_file = None
    file_content = None
    if last_file_row:
        last_file = last_file_row['filename']
        if last_file_row['is_sanitized']:
            try:
                with open(os.path.join(app.config['UPLOAD_FOLDER'], last_file), 'r', encoding='utf-8', errors='ignore') as f:
                    file_content = f.read()
            except: file_content = "Error reading file"
    conn.close()
    return render_template('secure.html', comments=comms, last_file=last_file, file_content=file_content)

if __name__ == '__main__':
    app.run(debug=True)