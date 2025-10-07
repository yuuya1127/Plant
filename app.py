from flask import Flask, render_template, request, jsonify
import requests
import base64
from io import BytesIO

app = Flask(__name__)

# PlantNet APIキー
PLANTNET_API_KEY = '2b105yVW1gUrILmTOZ3U7wTZXu'

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
        
        print(f"🌿 PlantNet APIにリクエスト送信中...")
        response = requests.post(
            f'https://my-api.plantnet.org/v2/identify/all?api-key={PLANTNET_API_KEY}',
            files=files,
            data=data
        )
        
        print(f"📡 レスポンス: {response.status_code}")
        
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
    print('📍 http://localhost:5000')
    print('='*50)
    app.run(debug=True, port=5000)