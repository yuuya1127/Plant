from flask import Flask, render_template, request, jsonify, redirect, flash, url_for,session
import requests
import base64
from io import BytesIO
from flask_cors import CORS
from db import get_connection
from datetime import timedelta
from flask import request

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
PLANTNET_API_KEY = '2b10udgkH4OFC14bAPk0saAEO'

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash("ユーザー名とパスワードを入力してください。")
            return redirect('/register')

        conn = get_connection()
        cursor = conn.cursor()

        # すでに登録済みか確認
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            flash("このユーザー名はすでに使われています。")
            return redirect(url_for("login_bp.login"))

        # ユーザー登録
        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password))
        conn.commit()
        cursor.close()
        conn.close()

        flash('登録が完了しました。ログインしてください。', 'success')
        return redirect('/login')
    
    return render_template('register.html')

@app.route("/login", methods=["GET", "POST"])
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
                # ログイン成功時のみアニメーション表示
                session["username"] = user["username"]
                session["user_id"] = user["id"]
                session["login_success"] = True  # 成功フラグ
                return render_template("login.html", username=username, success=True)

    return render_template("login.html", error=error)


@app.route("/user_info")
def user_info():
    # ログインしていない場合はログイン画面へ戻す
    if "username" not in session:
        flash("ログインしてください。")
        return redirect(url_for("login"))

    return render_template("user_info.html", username=session["username"])


@app.route("/logout")
def logout():
    session.clear()
    flash("ログアウトしました。")
    return redirect(url_for("login"))


@app.route('/')
def index():
    """画像選択画面"""
    return render_template('index.html')

@app.route('/identify', methods=['POST'])
def identify():
    """植物識別処理"""
    try:
        # アップロードされた画像を取得
        if 'image' not in request.files:
            return jsonify({'error': '画像がアップロードされていません'}), 400
        
        image_file = request.files['image']
        
        if image_file.filename == '':
            return jsonify({'error': '画像が選択されていません'}), 400
        
        # 画像をバイナリで読み込み
        image_data = image_file.read()
        
        # PlantNet APIにリクエスト
        files = {
            'images': (image_file.filename, BytesIO(image_data), image_file.content_type)
        }
        data = {
            'organs': 'auto'
        }
        
        print(f"PlantNet APIにリクエスト送信中...")
        response = requests.post(
            f'https://my-api.plantnet.org/v2/identify/all?api-key={PLANTNET_API_KEY}',
            files=files,
            data=data
        )
        
        print(f"レスポンス: {response.status_code}")
        
        if response.status_code != 200:
            return jsonify({'error': f'API Error: {response.status_code}'}), response.status_code
        
        result = response.json()
        
        # 画像をBase64エンコード（結果画面で表示するため）
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        image_url = f"data:{image_file.content_type};base64,{image_base64}"
        
        print(f"✅ 識別成功: {len(result.get('results', []))}件の結果")
        
        return jsonify({
            'success': True,
            'image_url': image_url,
            'results': result.get('results', [])
        })
        
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/result')
def result():
    """結果表示画面"""
    return render_template('result.html')

if __name__ == '__main__':
    print('='*50)
    print(' PlantNet 植物識別アプリを起動中...')
    print('http://localhost:5001')
    print('='*50)
    app.run(debug=True, port=5001, host="127.0.0.1")

