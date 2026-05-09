import os
import uuid
import random
import subprocess
import sqlite3
import socket
import tempfile
from datetime import datetime

from flask import Flask, request, jsonify, send_file, render_template
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
from qrcode import QRCode
from qrcode.image.pil import PilImage
import io

# ---------- 配置 ----------
UPLOAD_FOLDER = 'uploads'
DATABASE = 'sessions.db'
SESSION_CODE = ''.join(random.choices('0123456789', k=6))  # 6位随机数字码
PORT = 8080

# ---------- 获取本机局域网 IP ----------
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

LOCAL_IP = get_local_ip()

# ---------- 初始化数据库 ----------
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room TEXT NOT NULL,
            sender TEXT,
            type TEXT NOT NULL,        -- "text", "file"
            content TEXT,              -- 文本内容 或 文件名
            file_path TEXT,            -- 文件存储路径（仅文件消息）
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# ---------- 文件搜索支持 ----------
def search_files(query, room):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        SELECT sender, type, content, file_path, timestamp FROM messages
        WHERE room = ? AND (type = 'file' AND content LIKE ? OR type = 'text' AND content LIKE ?)
        ORDER BY timestamp DESC
        LIMIT 50
    ''', (room, f'%{query}%', f'%{query}%'))
    results = c.fetchall()
    conn.close()
    return results

# ---------- PDF 转换（使用 LibreOffice 完整路径）----------
def convert_to_pdf(file_path):
    """ 使用 LibreOffice 转换为 PDF，返回 PDF 文件路径 """
    if not os.path.exists(file_path):
        return None
    output_dir = tempfile.mkdtemp()
    # Windows 下 LibreOffice 可执行文件为 soffice.exe，请根据实际安装路径调整
    soffice_path = r'C:\Program Files\LibreOffice\program\soffice.exe'
    if not os.path.exists(soffice_path):
        # 如果不在默认路径，可以尝试用常见的备用路径
        soffice_path = r'C:\Program Files (x86)\LibreOffice\program\soffice.exe'
    try:
        subprocess.run([
            soffice_path, '--headless', '--convert-to', 'pdf',
            '--outdir', output_dir, file_path
        ], timeout=30, check=True)
        # 查找生成的 PDF 文件
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        pdf_path = os.path.join(output_dir, f'{base_name}.pdf')
        if os.path.exists(pdf_path):
            return pdf_path
        return None
    except Exception as e:
        print(f'PDF转换失败: {e}')
        return None

# ---------- 应用初始化 ----------
app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'local-share-secret'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
socketio = SocketIO(app, cors_allowed_origins="*")

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
init_db()

# ---------- 路由 ----------
@app.route('/')
def index():
    return render_template('index.html',
                         session_code=SESSION_CODE,
                         local_ip=LOCAL_IP,
                         port=PORT)

@app.route('/qr')
def generate_qr():
    url = f'http://{LOCAL_IP}:{PORT}?code={SESSION_CODE}'
    qr = QRCode()
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/check_code', methods=['POST'])
def check_code():
    data = request.json
    code = data.get('code', '')
    if code == SESSION_CODE:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False})

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': '没有文件'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400

    original_name = file.filename
    ext = os.path.splitext(original_name)[1]
    saved_name = f'{uuid.uuid4()}{ext}'
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], saved_name)
    file.save(save_path)

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('INSERT INTO messages (room, sender, type, content, file_path) VALUES (?,?,?,?,?)',
              (SESSION_CODE, request.remote_addr, 'file', original_name, saved_name))
    conn.commit()
    conn.close()

    socketio.emit('new_message', {
        'sender': request.remote_addr,
        'type': 'file',
        'content': original_name,
        'file_path': saved_name,
        'timestamp': datetime.now().strftime('%H:%M:%S')
    }, room=SESSION_CODE)

    return jsonify({'success': True, 'file_name': original_name})

@app.route('/download/<filename>')
def download_file(filename):
    safe_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(safe_path):
        return '文件不存在', 404
    return send_file(safe_path, as_attachment=True, download_name=filename)

@app.route('/pdf/<filename>')
def pdf_version(filename):
    original_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    pdf_path = convert_to_pdf(original_path)
    if not pdf_path:
        return '转换失败（请检查 LibreOffice 是否已安装）', 500
    base = os.path.splitext(filename)[0]
    return send_file(pdf_path, as_attachment=True, download_name=f'{base}.pdf')

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    results = search_files(query, SESSION_CODE)
    messages = []
    for row in results:
        sender, mtype, content, file_path, timestamp = row
        messages.append({
            'sender': sender,
            'type': mtype,
            'content': content,
            'file_path': file_path,
            'timestamp': timestamp
        })
    return jsonify(messages)

# ---------- WebSocket 事件 ----------
@socketio.on('join')
def on_join(data):
    code = data.get('code', '')
    if code == SESSION_CODE:
        join_room(SESSION_CODE)
        emit('status', {'msg': '已加入会话'}, room=request.sid)
    else:
        emit('status', {'msg': '验证码错误'}, room=request.sid)

@socketio.on('chat_message')
def handle_chat(data):
    msg_text = data.get('message', '')
    sender = request.remote_addr
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('INSERT INTO messages (room, sender, type, content) VALUES (?,?,?,?)',
              (SESSION_CODE, sender, 'text', msg_text))
    conn.commit()
    conn.close()

    emit('new_message', {
        'sender': sender,
        'type': 'text',
        'content': msg_text,
        'timestamp': datetime.now().strftime('%H:%M:%S')
    }, room=SESSION_CODE)

# ---------- 启动 ----------
if __name__ == '__main__':
    print(f'=======================================')
    print(f' 会话码: {SESSION_CODE}')
    print(f' 请在浏览器打开: http://{LOCAL_IP}:{PORT}')
    print(f' 二维码地址: http://{LOCAL_IP}:{PORT}/qr')
    print(f'=======================================')
    socketio.run(app, host='0.0.0.0', port=PORT, debug=True, allow_unsafe_werkzeug=True)