from flask import Blueprint, render_template, request, session, redirect, url_for
from db import get_connection
from datetime import timedelta

login_bp = Blueprint("login_bp", __name__)

# -----------------------------------------
# 🔑 ログイン処理
# -----------------------------------------
@login_bp.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        # 入力チェック
        if not username or not password:
            error = "ユーザー名とパスワードを入力してください。"
            return render_template("login.html", error=error, success=False, username=username)

        # DB検索
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
            return render_template("login.html", error=error, success=False, username=username)

        # ログイン成功
        session["username"] = user["username"]
        session["user_id"] = user["id"]

        # ログイン後に user-info へ移動
        return redirect(url_for("login_bp.welcome"))

    return render_template("login.html", error="", success=False, username="")


# -----------------------------------------
# 🔑 ログアウト
# -----------------------------------------
@login_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_bp.login"))


# -----------------------------------------
# 🔑 ユーザー情報ページ
# -----------------------------------------
@login_bp.route("/user-info")
def welcome():
    username = session.get("username")

    if not username:
        return redirect(url_for("login_bp.login"))

    # ← message をここで渡す必要がある！
    return render_template("user_info.html", message=f"{username} さん、ログイン")


# -----------------------------------------
# 🔑 言語設定（ふりがななど）
# -----------------------------------------
@login_bp.route("/set_language", methods=["POST"])
def set_language():
    import json
    user_id = session.get("user_id")
    if not user_id:
        return {"success": False, "message": "ログインしてください"}

    data = request.get_json()
    language = data.get("language", "hiragana")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE user_settings SET language=%s WHERE user_id=%s",
        (language, user_id)
    )
    conn.commit()
    cursor.close()
    conn.close()

    return {"success": True, "message": "言語設定を更新しました"}