from flask import Flask, render_template, request, jsonify, redirect
import requests
import base64
from io import BytesIO
from flask_cors import CORS
from db import get_connection

#Blueprintをインポート
from routes.login_routes import login_bp


app = Flask(__name__)
CORS(app)
app.secret_key = "dev_secret"

#Blueprint登録
app.register_blueprint(login_bp)

# PlantNet APIキー
PLANTNET_API_KEY = '2b10udgkH4OFC14bAPk0saAEO'

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()

        # バリデーション
        if not username or not password:
            return render_template('register.html', error="ユーザー名とパスワードを入力してください。")

        # DBに接続
        conn = get_connection()
        cursor = conn.cursor()

        # 既存ユーザー名のチェック
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return render_template('register.html', error="そのユーザー名は既に使われています。")

        # 新規登録
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, password)
        )
        conn.commit()
        cursor.close()
        conn.close()

        # 登録後はログイン画面へ
        return redirect('/')

    # GETの場合は単純に登録画面表示
    return render_template('register.html')

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
    print('🚀 PlantNet 植物識別アプリを起動中...')
    print('📍 http://localhost:5001')
    print('='*50)
    app.run(debug=True, port=5001, host="127.0.0.1")

