#!/usr/bin/env python3
"""
SMS API - ZTE modem integration
Secure token-based SMS sending + Admin panel
"""

from flask import (Flask, request, jsonify, session, render_template,
                   redirect, url_for, flash)
from functools import wraps
import sqlite3
import hashlib
import secrets
import json
import os
from datetime import datetime, timedelta
import re
import urllib.request
import urllib.parse

app = Flask(__name__)
def _get_secret_key():
    key_file = '/opt/sms-api/.secret_key'
    if os.path.exists(key_file):
        with open(key_file) as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(key_file, 'w') as f:
        f.write(key)
    os.chmod(key_file, 0o600)
    return key

app.secret_key = _get_secret_key()

DB_PATH     = '/opt/sms-api/tokens.db'
LOG_PATH    = '/var/log/sms-api.log'
ADMIN_CONF  = '/opt/sms-api/admin.conf'
ZTE_BASE    = 'http://192.168.0.1'

# ═══════════════════════════════════════════════
# Database
# ═══════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_hash TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT,
        max_sms_per_hour INTEGER DEFAULT 10,
        max_sms_per_day  INTEGER DEFAULT 50,
        enabled INTEGER DEFAULT 1
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS sms_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_id INTEGER,
        recipient TEXT NOT NULL,
        message TEXT NOT NULL,
        status TEXT NOT NULL,
        sent_at TEXT NOT NULL,
        FOREIGN KEY (token_id) REFERENCES tokens (id)
    )''')
    conn.commit()
    conn.close()

def log_event(message, level='INFO'):
    timestamp = datetime.now().isoformat()
    try:
        with open(LOG_PATH, 'a') as f:
            f.write(f"[{timestamp}] {level}: {message}\n")
    except Exception:
        pass

# ═══════════════════════════════════════════════
# Admin password
# ═══════════════════════════════════════════════

def get_admin_password():
    if os.path.exists(ADMIN_CONF):
        with open(ADMIN_CONF) as f:
            return f.read().strip()
    # Generate on first run
    pwd = secrets.token_urlsafe(16)
    with open(ADMIN_CONF, 'w') as f:
        f.write(pwd)
    os.chmod(ADMIN_CONF, 0o600)
    print(f"\n{'='*50}")
    print(f"  Admin slaptažodis: {pwd}")
    print(f"  Išsaugotas: {ADMIN_CONF}")
    print(f"{'='*50}\n")
    return pwd

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

# ═══════════════════════════════════════════════
# API Token auth
# ═══════════════════════════════════════════════

def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()

def validate_token(token):
    if not token or len(token) < 32:
        return None
    token_hash = hash_token(token)
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, expires_at FROM tokens WHERE token_hash=? AND enabled=1', (token_hash,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    if row['expires_at']:
        if datetime.now() > datetime.fromisoformat(row['expires_at']):
            return None
    return row['id']

def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '')
        if token.startswith('Bearer '):
            token = token[7:]
        token_id = validate_token(token)
        if not token_id:
            log_event(f"Invalid token from {request.remote_addr}", "WARN")
            return jsonify({'error': 'Invalid or expired token'}), 401
        request.token_id = token_id
        return f(*args, **kwargs)
    return decorated

# ═══════════════════════════════════════════════
# Rate limiting
# ═══════════════════════════════════════════════

def check_rate_limit(token_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT max_sms_per_hour, max_sms_per_day FROM tokens WHERE id=?', (token_id,))
    limits = c.fetchone()
    if not limits:
        conn.close()
        return False, "Token not found"
    now = datetime.now()
    hour_ago = (now - timedelta(hours=1)).isoformat()
    day_ago  = (now - timedelta(days=1)).isoformat()
    c.execute("SELECT COUNT(*) FROM sms_log WHERE token_id=? AND sent_at>? AND status='sent'",
              (token_id, hour_ago))
    count_hour = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM sms_log WHERE token_id=? AND sent_at>? AND status='sent'",
              (token_id, day_ago))
    count_day = c.fetchone()[0]
    conn.close()
    if count_hour >= limits['max_sms_per_hour']:
        return False, f"Hourly limit exceeded ({count_hour}/{limits['max_sms_per_hour']})"
    if count_day >= limits['max_sms_per_day']:
        return False, f"Daily limit exceeded ({count_day}/{limits['max_sms_per_day']})"
    return True, "OK"

# ═══════════════════════════════════════════════
# ZTE Modem helpers
# ═══════════════════════════════════════════════

def text_to_ucs2(text):
    return ''.join([format(ord(c), '04X') for c in text])

def send_sms_modem(recipient, message):
    try:
        post_data = (
            f"isTest=false&goformId=SEND_SMS&notCallback=true&"
            f"Number={urllib.parse.quote(recipient)}&sms_time=&"
            f"MessageBody={text_to_ucs2(message)}&ID=-1&encode_type=UNICODE"
        ).encode('utf-8')
        req = urllib.request.Request(
            f"{ZTE_BASE}/goform/goform_set_cmd_process",
            data=post_data,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': f'{ZTE_BASE}/index.html'
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
        if result.get('result') == 'success':
            log_event(f"SMS sent to {recipient}: {message[:40]}", "INFO")
            return True, "SMS sent successfully"
        return False, f"Modem error: {result}"
    except Exception as e:
        log_event(f"SMS error: {e}", "ERROR")
        return False, str(e)

def get_modem_status():
    try:
        params = urllib.parse.urlencode({
            'isTest': 'false',
            'cmd': 'modem_main_state,signalbar,network_type,rssi,network_provider',
            'multi_data': '1'
        })
        req = urllib.request.Request(
            f"{ZTE_BASE}/goform/goform_get_cmd_process?{params}",
            headers={'Referer': f'{ZTE_BASE}/'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        return {
            'state':        data.get('modem_main_state', '—'),
            'signal_bars':  data.get('signalbar', '0'),
            'network_type': data.get('network_type', '—'),
            'rssi':         data.get('rssi', ''),
            'operator':     data.get('network_provider', '—'),
        }
    except Exception:
        return None

# ═══════════════════════════════════════════════
# API endpoints
# ═══════════════════════════════════════════════

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/api/sms/send', methods=['POST'])
@require_token
def api_send_sms():
    data = request.get_json()
    if not data or 'to' not in data or 'text' not in data:
        return jsonify({'error': 'Missing fields: to, text'}), 400
    recipient = data['to']
    message   = data['text']
    if not re.match(r'^\+?\d{7,15}$', recipient):
        return jsonify({'error': 'Invalid phone number'}), 400
    if len(message) > 201:
        return jsonify({'error': 'Message too long (max 201 chars)'}), 400
    allowed, reason = check_rate_limit(request.token_id)
    if not allowed:
        return jsonify({'error': reason}), 429
    success, msg = send_sms_modem(recipient, message)
    conn = get_db()
    conn.execute(
        "INSERT INTO sms_log (token_id,recipient,message,status,sent_at) VALUES (?,?,?,?,?)",
        (request.token_id, recipient, message, 'sent' if success else 'failed',
         datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    if success:
        return jsonify({'success': True, 'message': msg, 'to': recipient, 'length': len(message)})
    return jsonify({'error': msg}), 500

@app.route('/api/sms/status')
@require_token
def api_modem_status():
    m = get_modem_status()
    if not m:
        return jsonify({'error': 'Modem unreachable'}), 503
    return jsonify({'modem': 'ZTE WCDMA 19d2:1706', 'status': 'online', **m})

@app.route('/api/sms/stats')
@require_token
def api_stats():
    tid = request.token_id
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT max_sms_per_hour, max_sms_per_day FROM tokens WHERE id=?', (tid,))
    limits = c.fetchone()
    hour_ago = (datetime.now()-timedelta(hours=1)).isoformat()
    day_ago  = (datetime.now()-timedelta(days=1)).isoformat()
    c.execute("SELECT COUNT(*) FROM sms_log WHERE token_id=? AND sent_at>? AND status='sent'",
              (tid, hour_ago))
    count_hour = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM sms_log WHERE token_id=? AND sent_at>? AND status='sent'",
              (tid, day_ago))
    count_day = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM sms_log WHERE token_id=? AND status='sent'", (tid,))
    total = c.fetchone()[0]
    conn.close()
    return jsonify({'usage': {
        'hour':  {'used': count_hour, 'limit': limits['max_sms_per_hour']},
        'day':   {'used': count_day,  'limit': limits['max_sms_per_day']},
        'total': total
    }})

# ═══════════════════════════════════════════════
# Admin panel
# ═══════════════════════════════════════════════

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        pwd = request.form.get('password', '')
        if pwd == get_admin_password():
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        return render_template('admin_login.html', error='Neteisingas slaptažodis')
    return render_template('admin_login.html', error=None)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))

@app.route('/admin')
@require_admin
def admin_dashboard():
    conn = get_db()
    c = conn.cursor()

    # Stats
    c.execute("SELECT COUNT(*) FROM sms_log WHERE status='sent'")
    total_sent = c.fetchone()[0]
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute("SELECT COUNT(*) FROM sms_log WHERE status='sent' AND sent_at LIKE ?", (f'{today}%',))
    sent_today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM sms_log WHERE status='failed' AND sent_at LIKE ?", (f'{today}%',))
    failed_today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM tokens WHERE enabled=1")
    active_tokens = c.fetchone()[0]

    # Chart: last 7 days
    chart_labels, chart_sent, chart_failed = [], [], []
    for i in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        chart_labels.append((datetime.now() - timedelta(days=i)).strftime('%m-%d'))
        c.execute("SELECT COUNT(*) FROM sms_log WHERE status='sent' AND sent_at LIKE ?", (f'{day}%',))
        chart_sent.append(c.fetchone()[0])
        c.execute("SELECT COUNT(*) FROM sms_log WHERE status='failed' AND sent_at LIKE ?", (f'{day}%',))
        chart_failed.append(c.fetchone()[0])

    # Recent SMS
    c.execute('''SELECT l.id, l.recipient, l.message, l.status, l.sent_at, t.name as token_name
                 FROM sms_log l LEFT JOIN tokens t ON l.token_id=t.id
                 ORDER BY l.id DESC LIMIT 10''')
    recent_sms = [dict(r) for r in c.fetchall()]

    conn.close()
    modem = get_modem_status()
    return render_template('admin_dashboard.html',
        active_page='dashboard',
        stats={'total_sent': total_sent, 'sent_today': sent_today,
               'failed_today': failed_today, 'active_tokens': active_tokens},
        chart_labels=chart_labels, chart_sent=chart_sent, chart_failed=chart_failed,
        recent_sms=recent_sms, modem=modem
    )

@app.route('/admin/tokens')
@require_admin
def admin_tokens():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM tokens ORDER BY id DESC')
    rows = [dict(r) for r in c.fetchall()]
    today = datetime.now().strftime('%Y-%m-%d')
    day_ago = (datetime.now()-timedelta(days=1)).isoformat()
    for t in rows:
        c.execute("SELECT COUNT(*) FROM sms_log WHERE token_id=? AND sent_at>? AND status='sent'",
                  (t['id'], day_ago))
        t['used_today'] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM sms_log WHERE token_id=? AND status='sent'", (t['id'],))
        t['total_sent'] = c.fetchone()[0]
    conn.close()
    return render_template('admin_tokens.html',
        active_page='tokens', tokens=rows, new_token=None)

@app.route('/admin/tokens/create', methods=['POST'])
@require_admin
def admin_tokens_create():
    name        = request.form.get('name', '').strip()
    max_hour    = int(request.form.get('max_per_hour', 10))
    max_day     = int(request.form.get('max_per_day', 50))
    expires_raw = request.form.get('expires_at', '').strip()
    expires_at  = (expires_raw + 'T23:59:59') if expires_raw else None

    if not name:
        flash('Pavadinimas privalomas', 'danger')
        return redirect(url_for('admin_tokens'))

    raw_token  = secrets.token_urlsafe(32)
    token_hash = hash_token(raw_token)
    conn = get_db()
    conn.execute(
        "INSERT INTO tokens (token_hash,name,created_at,expires_at,max_sms_per_hour,max_sms_per_day) VALUES (?,?,?,?,?,?)",
        (token_hash, name, datetime.now().isoformat(), expires_at, max_hour, max_day)
    )
    conn.commit()
    conn.close()

    # Show new token once
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM tokens ORDER BY id DESC')
    rows = [dict(r) for r in c.fetchall()]
    today = datetime.now().strftime('%Y-%m-%d')
    day_ago = (datetime.now()-timedelta(days=1)).isoformat()
    for t in rows:
        c.execute("SELECT COUNT(*) FROM sms_log WHERE token_id=? AND sent_at>? AND status='sent'",
                  (t['id'], day_ago))
        t['used_today'] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM sms_log WHERE token_id=? AND status='sent'", (t['id'],))
        t['total_sent'] = c.fetchone()[0]
    conn.close()
    return render_template('admin_tokens.html',
        active_page='tokens', tokens=rows, new_token=raw_token)

@app.route('/admin/tokens/toggle/<int:tid>', methods=['POST'])
@require_admin
def admin_tokens_toggle(tid):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT enabled FROM tokens WHERE id=?', (tid,))
    row = c.fetchone()
    if row:
        conn.execute('UPDATE tokens SET enabled=? WHERE id=?', (0 if row['enabled'] else 1, tid))
        conn.commit()
    conn.close()
    return redirect(url_for('admin_tokens'))

@app.route('/admin/tokens/delete/<int:tid>', methods=['POST'])
@require_admin
def admin_tokens_delete(tid):
    conn = get_db()
    conn.execute('DELETE FROM tokens WHERE id=?', (tid,))
    conn.execute('UPDATE sms_log SET token_id=NULL WHERE token_id=?', (tid,))
    conn.commit()
    conn.close()
    flash('Tokenas ištrintas', 'success')
    return redirect(url_for('admin_tokens'))

@app.route('/admin/tokens/stats/<int:tid>')
@require_admin
def admin_tokens_stats(tid):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT max_sms_per_hour, max_sms_per_day FROM tokens WHERE id=?', (tid,))
    limits = c.fetchone()
    if not limits:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    hour_ago = (datetime.now()-timedelta(hours=1)).isoformat()
    day_ago  = (datetime.now()-timedelta(days=1)).isoformat()
    c.execute("SELECT COUNT(*) FROM sms_log WHERE token_id=? AND sent_at>? AND status='sent'",
              (tid, hour_ago))
    used_hour = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM sms_log WHERE token_id=? AND sent_at>? AND status='sent'",
              (tid, day_ago))
    used_day = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM sms_log WHERE token_id=? AND status='sent'", (tid,))
    total = c.fetchone()[0]
    c.execute("SELECT sent_at FROM sms_log WHERE token_id=? ORDER BY id DESC LIMIT 1", (tid,))
    last = c.fetchone()
    conn.close()
    return jsonify({
        'used_hour': used_hour, 'max_hour': limits['max_sms_per_hour'],
        'used_day':  used_day,  'max_day':  limits['max_sms_per_day'],
        'total':     total,
        'last_sms':  last['sent_at'][:16] if last else None
    })

@app.route('/admin/logs')
@require_admin
def admin_logs():
    page     = int(request.args.get('page', 1))
    per_page = 50
    offset   = (page - 1) * per_page
    tid_filter    = request.args.get('token_id', '')
    status_filter = request.args.get('status', '')

    conn = get_db()
    c = conn.cursor()

    where, params = [], []
    if tid_filter:
        where.append('l.token_id=?'); params.append(tid_filter)
    if status_filter:
        where.append('l.status=?'); params.append(status_filter)
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

    c.execute(f'SELECT COUNT(*) FROM sms_log l {where_sql}', params)
    total = c.fetchone()[0]

    c.execute(f'''SELECT l.*, t.name as token_name FROM sms_log l
                  LEFT JOIN tokens t ON l.token_id=t.id
                  {where_sql} ORDER BY l.id DESC LIMIT ? OFFSET ?''',
              params + [per_page, offset])
    logs = [dict(r) for r in c.fetchall()]

    c.execute('SELECT id, name FROM tokens ORDER BY name')
    tokens = [dict(r) for r in c.fetchall()]
    conn.close()

    return render_template('admin_logs.html',
        active_page='logs', logs=logs, tokens=tokens,
        total=total, page=page, per_page=per_page,
        selected_token=tid_filter, selected_status=status_filter
    )

@app.route('/admin/modem', methods=['GET'])
@require_admin
def admin_modem():
    return render_template('admin_modem.html',
        active_page='modem', modem=get_modem_status(), test_result=None)

@app.route('/admin/modem/test-sms', methods=['POST'])
@require_admin
def admin_modem_test():
    phone   = request.form.get('phone', '').strip()
    message = request.form.get('message', '').strip()
    success, msg = send_sms_modem(phone, message)
    return render_template('admin_modem.html',
        active_page='modem', modem=get_modem_status(),
        test_result={'success': success, 'error': msg if not success else None}
    )

# ═══════════════════════════════════════════════
# Init & run
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    init_db()
    get_admin_password()  # generate if missing
    log_event("SMS API starting...", "INFO")
    app.run(host='0.0.0.0', port=5000, debug=False)
