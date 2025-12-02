from flask import Flask, render_template, request, jsonify, redirect, flash, url_for,session
import requests
import base64
from io import BytesIO
from flask_cors import CORS
from db import get_connection
from datetime import timedelta
from flask import request
from google import genai

#Blueprintをインポート
from routes.login_routes import login_bp


app = Flask(__name__)
CORS(app)
app.secret_key = "dev_secret"
app.permanent_session_lifetime = timedelta(minutes=30)

@app.before_request
def clear_session_on_start():
    # 最初のリクエスト時のみログイン情報を削除
    if 'initialized' not in session:
        session.clear()
        session['initialized'] = True

#Blueprint登録
app.register_blueprint(login_bp)

# PlantNet APIキー
PLANTNET_API_KEY = '2b10kyDU7O4G8EU6G1INHSe8wu'

# Gemini APIキー
GEMINI_API_KEY = "AIzaSyAx1PDAWgDXuxL4W0Wrz9rQRkQ0WInDqt8"

# === Gemini説明生成関数 ===
def get_gemini_description(plant_name):
    client = genai.Client(api_key=GEMINI_API_KEY)
 
    prompt = f"""
    次の植物について日本語で説明してください。
    - 植物名: {plant_name}
    以下の項目をそれぞれ「花言葉」「由来」「栽培方法」「特徴」という見出しの下に出力してください。
    出力フォーマットは以下のようにしてください。
 
    花言葉:（ここに説明）
    由来:（ここに説明）
    栽培方法:（ここに説明）
    特徴:（ここに説明）
    """
 
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
 
    text = response.text
 
    # 出力を項目ごとに分割して整理
    sections = {"花言葉": "", "由来": "", "栽培方法": "", "特徴": ""}
    current_key = None
 
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for key in sections.keys():
            if line.startswith(key + ":"):
                current_key = key
                sections[key] = line[len(key) + 1:].strip()
                break
        else:
            if current_key:
                sections[current_key] += "\n" + line
 
    return sections


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        # 入力チェック
        if not username or not password:
            flash("ユーザー名とパスワードを入力してください。")
            return render_template("register.html", error="ユーザー名とパスワードを入力してください")

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # すでに登録されているか確認
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            # ❗ ログイン画面に飛ばさず register.html に戻す
            return render_template("register.html", error="このユーザー名はすでに使われています。")

        # 新規登録
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, password)
        )
        conn.commit()

        cursor.close()
        conn.close()

        flash("登録が完了しました。ログインしてください。", "success")
        return redirect(url_for("login_bp.login"))  # ← OK

    # GET時は通常の画面表示
    return render_template('register.html')

@login_bp.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            error = "ユーザー名とパスワードを入力してください。"
            return render_template("login.html", error=error, success=False, username=username)

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

        # ★ ログイン成功 ★
        session["username"] = user["username"]
        session["user_id"] = user["id"]

        # ★ 正しく index に飛ぶコード
        return redirect(url_for("index"))

    return render_template("login.html", error="", success=False)

@login_bp.route("/user-info")
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

    # 🔹 username も一緒にテンプレートへ渡すように修正
    return render_template("user_info.html", message=message, username=username)

@app.route("/history")
def history():
    return render_template("history.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("ログアウトしました。")
    return redirect(url_for("login_bp.login"))

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files.get("file")
        if file:
            # ここでアップロード処理
            file.save(f"./uploads/{file.filename}")
        return redirect(url_for("upload"))
    return render_template("upload.html")


@app.route('/')
def index():
    """画像選択画面"""
    return render_template('index.html')

# === 植物識別 API ===
@app.route('/identify', methods=['POST'])
def identify():
    """植物識別処理"""
    try:
        if 'image' not in request.files:
            return jsonify({'error': '画像がアップロードされていません'}), 400
 
        image_file = request.files['image']
        if image_file.filename == '':
            return jsonify({'error': '画像が選択されていません'}), 400
 
        image_data = image_file.read()
        files = {'images': (image_file.filename, BytesIO(image_data), image_file.content_type)}
        data = {'organs': 'auto'}
 
        response = requests.post(
            f'https://my-api.plantnet.org/v2/identify/all?api-key={PLANTNET_API_KEY}',
            files=files,
            data=data
        )
 
        if response.status_code != 200:
            return jsonify({'error': f'API Error: {response.status_code}'}), response.status_code
 
        result = response.json()
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        image_url = f"data:{image_file.content_type};base64,{image_base64}"
 
        # 一番確信度の高い植物名を取得
        if len(result.get('results', [])) > 0:
            top_plant_name = result['results'][0]['species']['scientificNameWithoutAuthor']
        else:
            top_plant_name = None
 
        # 🔥 植物名が取れなかった場合の安全処理（重要）
        if top_plant_name:
            gemini_description = get_gemini_description(top_plant_name)
        else:
            gemini_description = {
                "花言葉": "植物名が特定できなかったため説明を生成できませんでした。",
                "由来": "植物名が特定できなかったため説明を生成できませんでした。",
                "栽培方法": "植物名が特定できなかったため説明を生成できませんでした。",
                "特徴": "植物名が特定できなかったため説明を生成できませんでした。"
            }
 
        return jsonify({
            'success': True,
            'image_url': image_url,
            'results': result.get('results', []),
            'gemini_description': gemini_description
        })
 
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500
 
 
# === 結果表示 ===
@app.route('/result')
def result():
    return render_template('result.html')
 
 
# === 起動 ===
if __name__ == '__main__':
    print('=' * 50)
    print('🚀 PlantNet 植物識別アプリを起動中...')
    print('📍 http://localhost:5001')
    print('=' * 50)
    app.run(debug=True, port=5001, host="127.0.0.1")

