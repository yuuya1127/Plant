from flask import Blueprint, render_template, request, session, redirect, url_for
from db import get_connection  # ← DB接続関数を忘れずに
from datetime import timedelta

login_bp = Blueprint("login_bp", __name__)

# セッションの有効期限（例：30分）
# app.py 側で app.permanent_session_lifetime = timedelta(minutes=30) を設定してもOK

@login_bp.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            error = "ユーザー名とパスワードを入力してください。"
        else:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM users WHERE BINARY username = %s AND BINARY password = %s",
                (username, password)
            )
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if not user:
                error = "ユーザー名またはパスワードが違います。"
            else:
                # 🔹 セッションに保存して「ログイン済み」として扱う
                session["username"] = username
                session["just_logged_in"] = True  # ← ログイン直後だけ True
                return redirect(url_for("login_bp.welcome"))  # ログイン後に別画面へ

    return render_template("login.html", error=error)


@login_bp.route("/welcome")
def welcome():
    username = session.get("username")
    just_logged_in = session.pop("just_logged_in", False)  # 一度だけ取り出して削除

    if not username:
        # 未ログインならログインページへ戻す
        return redirect(url_for("login_bp.login"))

    # just_logged_in が True のときだけ演出を出す
    if just_logged_in:
        message = f"ようこそ、{username} さん！"
    else:
        message = f"{username} さん、こんにちは。"

    return render_template("welcome.html", message=message)
