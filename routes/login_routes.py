from flask import Blueprint, render_template, request, redirect, url_for, session
from db import get_connection  # ← これを追加

login_bp = Blueprint('login', __name__)

# --- ログイン画面 ---
@login_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            session['user'] = username
            return redirect(url_for('index'))  # 植物識別画面へ
        else:
            return render_template('login.html', error="ユーザー名またはパスワードが違います")

    return render_template('login.html')


# --- 新規登録画面 ---
@login_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_connection()
        cursor = conn.cursor()

        # 同じユーザー名が存在するか確認
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        existing = cursor.fetchone()

        if existing:
            conn.close()
            return render_template('register.html', error="このユーザー名は既に使われています")

        # 新規ユーザーを登録
        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password))
        conn.commit()
        conn.close()

        return redirect(url_for('login.login'))  # 登録後にログイン画面へ

    return render_template('register.html')

