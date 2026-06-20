# -*- coding: utf-8 -*-
"""
新大新物流园 - 供应商送货预约系统
云部署版本 (Render.com / PythonAnywhere 兼容)
"""
import sqlite3
import os
from datetime import datetime, date
from flask import Flask, request, jsonify, g
from flask_cors import CORS

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# 云平台兼容：优先使用环境变量 PORT，否则默认 5100
PORT = int(os.environ.get('PORT', 5100))

# 数据库路径：Render 使用 /opt/render/project/src/，本地使用当前目录
DB_DIR = os.environ.get('RENDER_PROJECT_DIR', os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(DB_DIR, 'appointments.db')

ADMIN_TOKEN = 'huahan2026'

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db:
        db.close()

def init_db():
    """创建预约表"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_date TEXT NOT NULL,
            supplier_name TEXT NOT NULL,
            driver_phone TEXT NOT NULL,
            plate_number TEXT NOT NULL,
            product_name TEXT NOT NULL,
            piece_count INTEGER NOT NULL,
            weight REAL NOT NULL,
            volume REAL DEFAULT 0,
            unload_method TEXT NOT NULL,
            remark TEXT DEFAULT '',
            status TEXT DEFAULT '待审核',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    ''')
    conn.commit()
    conn.close()
    print('[DB] 数据库初始化完成: ' + DB_PATH)


# ============================================================
# API: 提交预约（司机端）
# ============================================================
@app.route('/api/appointment', methods=['POST'])
def create_appointment():
    data = request.json
    required = ['appointment_date', 'supplier_name', 'driver_phone', 'plate_number',
                'product_name', 'piece_count', 'weight', 'unload_method']
    
    for field in required:
        if field not in data or str(data[field]).strip() == '':
            return jsonify({'success': False, 'message': f'缺少必填项: {field}'}), 400
    
    db = get_db()
    db.execute('''
        INSERT INTO appointments (appointment_date, supplier_name, driver_phone, plate_number,
            product_name, piece_count, weight, unload_method, remark)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data['appointment_date'],
        data['supplier_name'].strip(),
        data['driver_phone'].strip(),
        data['plate_number'].strip(),
        data['product_name'].strip(),
        int(data['piece_count']),
        float(data['weight']),
        data['unload_method'].strip(),
        data.get('remark', '').strip()
    ))
    db.commit()
    
    appt_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    return jsonify({'success': True, 'message': '预约成功!', 'id': appt_id})


# ============================================================
# API: 获取预约列表（管理后台）
# ============================================================
@app.route('/api/appointments', methods=['GET'])
def get_appointments():
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    status = request.args.get('status', '')
    
    db = get_db()
    query = 'SELECT * FROM appointments WHERE 1=1'
    params = []
    
    if date_from:
        query += ' AND appointment_date >= ?'
        params.append(date_from)
    if date_to:
        query += ' AND appointment_date <= ?'
        params.append(date_to)
    if status:
        query += ' AND status = ?'
        params.append(status)
    
    query += ' ORDER BY appointment_date DESC, created_at DESC'
    rows = db.execute(query, params).fetchall()
    
    return jsonify({
        'success': True,
        'count': len(rows),
        'data': [dict(r) for r in rows]
    })


# ============================================================
# API: 更新预约状态（审核 + 物流状态）
# ============================================================
@app.route('/api/appointment/<int:appt_id>/status', methods=['PUT'])
def update_status(appt_id):
    data = request.json
    new_status = data.get('status', '')
    
    if new_status not in ['待审核', '已通过', '已拒绝', '已到仓', '已完成', '已取消']:
        return jsonify({'success': False, 'message': '无效状态'}), 400
    
    db = get_db()
    db.execute('UPDATE appointments SET status = ?, updated_at = datetime("now","localtime") WHERE id = ?',
               (new_status, appt_id))
    db.commit()
    
    return jsonify({'success': True, 'message': '状态更新成功'})


# ============================================================
# API: 司机查询预约状态（按手机号）
# ============================================================
@app.route('/api/check-status', methods=['GET'])
def check_status():
    phone = request.args.get('phone', '').strip()
    if not phone:
        return jsonify({'success': False, 'message': '请输入手机号码'}), 400
    
    db = get_db()
    rows = db.execute(
        'SELECT * FROM appointments WHERE driver_phone = ? ORDER BY created_at DESC LIMIT 20',
        (phone,)
    ).fetchall()
    
    return jsonify({
        'success': True,
        'count': len(rows),
        'data': [dict(r) for r in rows]
    })


# ============================================================
# API: 获取单条预约详情
# ============================================================
@app.route('/api/appointment/<int:appt_id>', methods=['GET'])
def get_appointment(appt_id):
    db = get_db()
    row = db.execute('SELECT * FROM appointments WHERE id = ?', (appt_id,)).fetchone()
    if not row:
        return jsonify({'success': False, 'message': '预约不存在'}), 404
    return jsonify({'success': True, 'data': dict(row)})


# ============================================================
# API: 统计概览
# ============================================================
@app.route('/api/stats', methods=['GET'])
def get_stats():
    target_date = request.args.get('date', date.today().isoformat())
    db = get_db()
    
    total = db.execute('SELECT COUNT(*) FROM appointments WHERE appointment_date = ?', 
                       (target_date,)).fetchone()[0]
    pending = db.execute('SELECT COUNT(*) FROM appointments WHERE appointment_date = ? AND status = "待审核"', 
                         (target_date,)).fetchone()[0]
    approved = db.execute('SELECT COUNT(*) FROM appointments WHERE appointment_date = ? AND status = "已通过"', 
                          (target_date,)).fetchone()[0]
    rejected = db.execute('SELECT COUNT(*) FROM appointments WHERE appointment_date = ? AND status = "已拒绝"', 
                          (target_date,)).fetchone()[0]
    arrived = db.execute('SELECT COUNT(*) FROM appointments WHERE appointment_date = ? AND status = "已到仓"', 
                         (target_date,)).fetchone()[0]
    completed = db.execute('SELECT COUNT(*) FROM appointments WHERE appointment_date = ? AND status = "已完成"', 
                           (target_date,)).fetchone()[0]
    
    return jsonify({
        'success': True,
        'stats': {
            'date': target_date,
            'total': total,
            'pending': pending,
            'approved': approved,
            'rejected': rejected,
            'arrived': arrived,
            'completed': completed
        }
    })


# ============================================================
# API: 健康检查
# ============================================================
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})


# ============================================================
# 页面路由
# ============================================================
@app.route('/')
def index():
    return app.send_static_file('driver.html')

@app.route('/admin')
def admin():
    return app.send_static_file('admin.html')


# ============================================================
# 启动入口
# ============================================================
if __name__ == '__main__':
    init_db()
    print('=' * 60)
    print('  新大新物流园 - 供应商送货预约平台')
    print(f'  端口: {PORT}')
    print(f'  数据库: {DB_PATH}')
    print('=' * 60)
    app.run(host='0.0.0.0', port=PORT, debug=False)
