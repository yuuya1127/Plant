from flask import Blueprint, render_template, request
from db import get_connection

login_bp = Blueprint("login_bp", __name__)

@login_bp.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        # 入力チェック
        if not username and not password:
            error = "ユーザー名とパスワードが未入力です。"
        elif not username:
            error = "ユーザー名が未入力です。"
        elif not password:
            error = "パスワードが未入力です。"
        else:
            # DB確認（両方一致）
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM users WHERE username=%s AND password=%s",
                (username, password)
            )
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if not user:
                error = "ユーザー名またはパスワードが違います。"
            else:
                # ログイン成功
                return f"{username} さんログイン成功！"  # 仮の画面

    return render_template("login.html", error=error)
