from flask import Flask, render_template, request, jsonify, redirect, flash, url_for, session
import requests
import base64
from io import BytesIO
from flask_cors import CORS
from db import get_connection
from datetime import timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from PIL import Image
import io
import google.generativeai as genai  
from flask import Flask, request, jsonify
import json

# Blueprintをインポート
from routes.login_routes import login_bp

app = Flask(__name__)
CORS(app)
app.secret_key = "dev_secret"
app.permanent_session_lifetime = timedelta(minutes=30)

# 画像保存先フォルダ
UPLOAD_FOLDER = "static/uploads" 
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.before_request
def clear_session_on_start():
    # 最初のリクエスト時のみログイン情報を削除
    if 'initialized' not in session:
        session.clear()
        session['initialized'] = True

# Blueprint登録
app.register_blueprint(login_bp)

# Plant.id APIキー
PLANT_ID_API_KEY = ""

# PlantNet APIキー
PLANTNET_API_KEY = ''

# Gemini APIキー
GEMINI_API_KEY = ""
# genaiライブラリの全体設定
genai.configure(api_key=GEMINI_API_KEY)

gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# === Gemini説明生成関数（既存のまま） ===
def get_gemini_description(plant_name):
    try:
        # ※説明生成は創造性が必要なため、デフォルトの設定を使用
        model = genai.GenerativeModel("gemini-2.5-flash")
    
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
    
        response = model.generate_content(prompt)
        text = response.text
    
        sections = {"花言葉": "", "由来": "", "栽培方法": "", "特徴": ""}
        current_key = None
    
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            
            clean_line = line.replace("*", "").replace("-", "").strip()
            is_header_line = False

            for key in sections.keys():
                if clean_line.startswith(key + ":") or clean_line.startswith(key + "："):
                    current_key = key
                    is_header_line = True
                    if ":" in clean_line:
                        content = clean_line.split(":", 1)[1]
                    elif "：" in clean_line:
                        content = clean_line.split("：", 1)[1]
                    else:
                        content = ""
                    sections[key] = content.strip()
                    break
            
            if not is_header_line and current_key:
                sections[current_key] += "\n" + line
    
        return sections

    except Exception as e:
        print(f"❌ Gemini Description Error: {str(e)}")
        return {
            "花言葉": "情報の取得に失敗しました",
            "由来": "",
            "栽培方法": "",
            "特徴": ""
        }

# === ★修正版：Gemini Vision で病気・害虫診断 ===
# ここを「信頼性向上版」に書き換えました
# === Plant.id + Gemini 連携診断関数 ===
def diagnose_plant_disease(image_data):
    """
    Plant.idで病気診断 → Geminiで詳細解説を生成
    
    処理フロー:
    1. Plant.id APIで画像から病気を診断
    2. 診断結果（病名・確信度）を取得
    3. Gemini APIに診断結果を渡して日本語で詳細解説を生成
    4. 症状・原因・対処法・予防方法をJSONで返す
    """
    try:
        print("\n" + "="*50)
        print("🔍 診断プロセス開始")
        print("="*50)
        
        # ステップ1: APIキーの確認
        print("\n【ステップ1】APIキー確認中...")
        if not PLANT_ID_API_KEY or PLANT_ID_API_KEY == "":
            print("❌ Plant.id APIキーが未設定")
            return create_error_response("Plant.id APIキーが設定されていません。")
        print("✅ Plant.id APIキー: OK")
        
        if not GEMINI_API_KEY or GEMINI_API_KEY == "":
            print("❌ Gemini APIキーが未設定")
            return create_error_response("Gemini APIキーが設定されていません。")
        print("✅ Gemini APIキー: OK")
        
        # ステップ2: 画像の最適化
        print("\n【ステップ2】画像を最適化中...")
        try:
            img = Image.open(io.BytesIO(image_data))
            print(f"📸 元画像サイズ: {img.size}")
            print(f"📸 元ファイルサイズ: {len(image_data) / 1024:.1f} KB")
            
            # Plant.idは2MP以下推奨、大きい画像はリサイズ
            max_size = 1600
            if img.width > max_size or img.height > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                print(f"📸 リサイズ後: {img.size}")
                
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=85)
                image_data = buffer.getvalue()
                print(f"📸 最適化後サイズ: {len(image_data) / 1024:.1f} KB")
        except Exception as e:
            print(f"⚠️ 画像処理エラー（継続）: {str(e)}")
        
        # ステップ3: Plant.id APIで病気診断
        print("\n【ステップ3】Plant.id APIで病気診断中...")
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        headers = {
            "Content-Type": "application/json",
            "Api-Key": PLANT_ID_API_KEY
        }
        
        payload = {
            "images": [image_base64],
            "latitude": 35.6895,
            "longitude": 139.6917,
            "similar_images": True,
            "health": "all"
        }

        print(f"📡 送信先: https://api.plant.id/v3/health_assessment")
        print(f"📡 リクエスト送信中...")
        
        response = requests.post(
            "https://api.plant.id/v3/health_assessment",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"📡 レスポンスコード: {response.status_code}")
        
        # エラーチェック
        if response.status_code not in [200, 201]:
            print(f"❌ Plant.id APIエラー")
            print(f"❌ レスポンス: {response.text[:500]}")
            
            error_msg = f"Plant.id APIエラー (コード: {response.status_code})"
            try:
                error_detail = response.json()
                if 'error' in error_detail:
                    error_msg = f"APIエラー: {error_detail['error']}"
                    print(f"❌ エラー詳細: {error_detail['error']}")
                elif 'message' in error_detail:
                    error_msg = f"APIエラー: {error_detail['message']}"
                    print(f"❌ エラーメッセージ: {error_detail['message']}")
            except:
                pass
            
            return create_error_response(error_msg)

        # Plant.idのレスポンスをパース
        res_data = response.json()
        print("✅ Plant.id APIレスポンス取得成功")
        
        # レスポンス構造の確認
        print(f"🔍 レスポンスキー: {list(res_data.keys())}")
        
        # ステップ4: 診断結果の抽出
        print("\n【ステップ4】診断結果を抽出中...")
        result = res_data.get('result', {})
        
        # 健康状態の判定
        is_healthy_data = result.get('is_healthy', {})
        is_healthy = is_healthy_data.get('binary', True)
        health_probability = is_healthy_data.get('probability', 0)
        
        print(f"🌿 健康状態: {'✅ 健康' if is_healthy else '⚠️ 病気の疑い'}")
        print(f"🌿 健康確率: {health_probability:.1%}")
        
        # 病気情報の取得
        disease_data = result.get('disease', {})
        suggestions = disease_data.get('suggestions', [])
        
        diagnosis_name = "健康（異常なし）"
        diagnosis_probability = 0
        diagnosis_description = ""
        
        if not is_healthy and suggestions:
            top_suggestion = suggestions[0]
            diagnosis_name = top_suggestion.get('name', '不明な病気')
            diagnosis_probability = top_suggestion.get('probability', 0)
            
            print(f"🦠 診断病名: {diagnosis_name}")
            print(f"🦠 確信度: {diagnosis_probability:.1%}")
            
            # Plant.idの詳細情報（あれば）
            details = top_suggestion.get('details', {})
            if details:
                diagnosis_description = details.get('description', '')
                print(f"📝 Plant.id説明: {diagnosis_description[:100]}...")
        else:
            print(f"✅ 診断結果: 健康な植物")
        
        # ステップ5: Gemini APIで詳細解説を生成
        print("\n【ステップ5】Gemini APIで日本語解説を生成中...")
        
        try:
            model = genai.GenerativeModel(
                "gemini-2.5-flash",
                generation_config={
                    "temperature": 0.4,
                    "top_p": 0.9,
                }
            )
            
            # Geminiへのプロンプト（診断結果を渡す）
            gemini_prompt = f"""
あなたは経験豊富な植物病理学者です。Plant.id APIによる診断結果を基に、初心者にもわかりやすく日本語で解説してください。

## Plant.idの診断結果
- 健康状態: {'健康' if is_healthy else '病気・害虫の疑い'}
- 診断名: {diagnosis_name}
- 確信度: {diagnosis_probability:.1%}
{f"- API説明: {diagnosis_description[:200]}" if diagnosis_description else ""}

## 指示
以下のJSON形式で必ず回答してください。マークダウン記法（```など）は使わないでください：

{{
    "健康状態": "{'健康' if is_healthy else '病気・害虫の疑い'}",
    "診断結果": "{diagnosis_name}",
    "症状": "この病気/状態で見られる具体的な症状を2-3文で説明してください",
    "原因": "この病気/状態が発生する主な原因を2-3文で説明してください",
    "対処法": "実践的な対処方法を具体的に3-5個、改行区切りで説明してください",
    "予防方法": "今後の予防策を2-3文で説明してください"
}}

重要: 純粋なJSONのみを出力してください。余計な説明やマークダウンは不要です。
"""
            
            print(f"🤖 Geminiにリクエスト送信...")
            gemini_response = model.generate_content(gemini_prompt)
            output_text = gemini_response.text.strip()
            
            print(f"🤖 Geminiレスポンス受信 ({len(output_text)} 文字)")
            print(f"🤖 レスポンス先頭: {output_text[:150]}...")
            
            # JSONパース
            parsed_result = parse_gemini_response(output_text)
            
            if parsed_result:
                print("✅ Gemini解析成功！")
                print("\n" + "="*50)
                print("✅ 診断完了")
                print("="*50 + "\n")
                return parsed_result
            else:
                print("⚠️ JSONパース失敗、フォールバック使用")
                return create_fallback_response(
                    is_healthy, 
                    diagnosis_name, 
                    diagnosis_probability,
                    diagnosis_description
                )
        
        except Exception as gemini_error:
            print(f"❌ Geminiエラー: {str(gemini_error)}")
            print(f"⚠️ Plant.idの結果のみ使用してフォールバック")
            return create_fallback_response(
                is_healthy,
                diagnosis_name,
                diagnosis_probability,
                diagnosis_description
            )
        
    except requests.exceptions.Timeout:
        print("❌ タイムアウトエラー")
        return create_error_response("通信がタイムアウトしました。ネットワーク接続を確認してください。")
    
    except requests.exceptions.ConnectionError:
        print("❌ 接続エラー")
        return create_error_response("Plant.id APIに接続できませんでした。ネットワーク接続を確認してください。")
    
    except requests.exceptions.RequestException as req_error:
        print(f"❌ 通信エラー: {str(req_error)}")
        return create_error_response(f"通信エラー: {str(req_error)}")
    
    except Exception as e:
        print(f"❌ 予期しないエラー: {str(e)}")
        import traceback
        traceback.print_exc()
        return create_error_response(f"診断処理エラー: {str(e)}")


def parse_gemini_response(text):
    """Geminiのレスポンスを安全にパースする"""
    try:
        # マークダウンのコードブロックを除去
        original_text = text
        
        if "```json" in text:
            parts = text.split("```json")
            if len(parts) > 1:
                text = parts[1].split("```")[0]
                print("🔧 Markdownブロックを除去")
        elif "```" in text:
            parts = text.split("```")
            if len(parts) >= 3:
                text = parts[1]
                print("🔧 コードブロックを除去")
        
        text = text.strip()
        
        # JSONパース試行
        data = json.loads(text)
        
        # 必須キーの確認
        required_keys = ["健康状態", "診断結果", "症状", "原因", "対処法", "予防方法"]
        missing_keys = [k for k in required_keys if k not in data]
        
        if missing_keys:
            print(f"⚠️ 必須キーが不足: {missing_keys}")
            return None
        
        print("✅ JSON構造が正常")
        return data
    
    except json.JSONDecodeError as e:
        print(f"⚠️ JSONパースエラー: {str(e)}")
        print(f"⚠️ パース対象（最初の200文字）:\n{text[:200]}")
        return None
    except Exception as e:
        print(f"⚠️ パース処理エラー: {str(e)}")
        return None


def create_error_response(error_message):
    """エラー時の標準レスポンス"""
    return {
        "健康状態": "診断失敗",
        "診断結果": "エラー",
        "症状": error_message,
        "原因": "以下の点を確認してください：\n• APIキーが正しく設定されているか\n• ネットワーク接続が正常か\n• Plant.idのクレジットが残っているか（https://admin.kindwise.com）",
        "対処法": "1. APIキーを確認してください\n2. 画像サイズを小さくしてみてください（1600×1600ピクセル以下推奨）\n3. ネットワーク接続を確認してください\n4. しばらく時間をおいて再試行してください",
        "予防方法": "鮮明な画像を使用し、病気や害虫が疑われる部分を中心に撮影してください。"
    }


def create_fallback_response(is_healthy, diagnosis_name, probability, description):
    """Gemini失敗時のフォールバック（Plant.idの結果を使用）"""
    health_status = "健康" if is_healthy else "病気・害虫の疑い"
    
    if is_healthy:
        return {
            "健康状態": health_status,
            "診断結果": diagnosis_name,
            "症状": "特に異常な症状は見られませんでした。葉の色や形状は正常な状態です。",
            "原因": "現時点では病気や害虫の明確な兆候は確認できませんでした。",
            "対処法": "• 引き続き適切な水やりを行ってください\n• 日光管理に注意してください\n• 定期的に植物の状態を観察してください\n• 葉の裏側もチェックしましょう",
            "予防方法": "風通しの良い場所で管理し、過湿を避けてください。定期的な観察を続けることで、早期発見・早期対処が可能になります。"
        }
    else:
        # Plant.idの説明があれば使用
        symptoms_text = description if description else f"{diagnosis_name}の症状が見られます（AI診断確信度: {probability:.1%}）。葉や茎の変色、斑点、萎れなどの異常が確認されました。"
        
        return {
            "健康状態": health_status,
            "診断結果": diagnosis_name,
            "症状": symptoms_text,
            "原因": "環境要因（温度、湿度、日照不足など）、病原菌の感染、または害虫による被害が考えられます。",
            "対処法": "• 病気の部分を清潔なハサミで取り除いてください\n• 適切な殺菌剤や殺虫剤の使用を検討してください\n• 風通しと日当たりを改善してください\n• 水やりの頻度を見直してください\n• 症状が深刻な場合は園芸専門家に相談してください",
            "予防方法": "定期的な観察、適切な水やり、良好な風通し、清潔な環境の維持が重要です。また、植物の免疫力を高めるため、適切な肥料を与えることも効果的です。"
        }

# ==========================================
# 修正済み：ユーザー登録（ハッシュ化して保存）
# ==========================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            return render_template("register.html", error="ユーザー名とパスワードを入力してください")

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE BINARY username = %s", (username,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return render_template("register.html", error="このユーザー名は既に使われています")
        
        # --- 修正箇所：ハッシュ化を無効化 ---
        # hashed_password = generate_password_hash(password) # コメントアウト
        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password))
        # ----------------------------------
        
        conn.commit()
        cursor.close()
        conn.close()
        flash("登録が完了しました。")
        return redirect(url_for("login_bp.login"))
    return render_template('register.html')

# ==========================================
# ★最重要修正：ログイン処理（自動復旧・デバッグ機能付き）
# ==========================================
@login_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE BINARY username = %s", (username,))
        user = cursor.fetchone()

        if user:
            # --- 修正箇所：単純な比較に変更 ---
            db_password = user["password"]
            if db_password == password:  # 直接比較
                session["username"] = user["username"]
                session["user_id"] = user["id"]
                cursor.close()
                conn.close()
                return redirect(url_for("index"))
            else:
                return render_template("login.html", error="ユーザー名またはパスワードが違います")
            # ----------------------------------
        else:
            return render_template("login.html", error="ユーザーが見つかりません")
    return render_template("login.html")

# ==========================================
# 練習用：パスワードリセット処理（平文保存版）
# ==========================================
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """パスワードリセットページ"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        # 入力チェック
        if not username or not new_password or not confirm_password:
            return render_template('forgot_password.html', 
                                error="すべての項目を入力してください")

        if new_password != confirm_password:
            return render_template('forgot_password.html', 
                                error="パスワードが一致しません",
                                username=username)

        if len(new_password) < 4:
            return render_template('forgot_password.html',
                                error="パスワードは4文字以上にしてください",
                                username=username)

        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            
            # ユーザーの存在確認
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            
            if not user:
                cursor.close()
                conn.close()
                return render_template('forgot_password.html', 
                                    error="ユーザー名が見つかりません")

            # === 修正箇所：ハッシュ化せず、入力されたパスワードをそのまま保存 ===
            # hashed_password = generate_password_hash(new_password)  # ←これを無効化
            cursor.execute(
                "UPDATE users SET password = %s WHERE id = %s",
                (new_password, user['id'])  # ← new_password を直接渡す
            )
            
            conn.commit()
            cursor.close()
            conn.close()

            print(f"✅ パスワードを更新しました (User: {username}, Pass: {new_password})")
            flash("パスワードがリセットされました。新しいパスワードでログインしてください。", "success")
            return redirect(url_for('login_bp.login'))
        
        except Exception as e:
            print(f"❌ DBエラー: {e}")
            return render_template('forgot_password.html',
                                error="エラーが発生しました。もう一度お試しください。")

    return render_template('forgot_password.html')


# ==========================================
# 移行用ツール（平文からハッシュへ一括変換）
# ==========================================
@app.route('/migrate-passwords-once')
def migrate_passwords():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, username, password FROM users")
        users = cursor.fetchall()
        
        migrated_count = 0
        for user in users:
            old_pass = user['password']
            # pbkdf2 などで始まっていない＝平文と判断
            if not old_pass.startswith(('pbkdf2:', 'scrypt:', 'bcrypt:')):
                new_hash = generate_password_hash(old_pass)
                cursor.execute(
                    "UPDATE users SET password = %s WHERE id = %s",
                    (new_hash, user['id'])
                )
                migrated_count += 1
        
        conn.commit()
        cursor.close()
        conn.close()
        return f"<h2>移行完了</h2><p>{migrated_count}件をハッシュ化しました。</p><a href='/login'>ログインへ</a>"
    except Exception as e:
        return f"エラー: {e}"


@login_bp.route("/user-info")
def welcome():
    username = session.get("username")
    just_logged_in = session.pop("just_logged_in", False)

    if not username:
        return redirect(url_for("login_bp.login"))

    if just_logged_in:
        message = f"ようこそ、{username} さん！"
    else:
        message = f"{username} さん、こんにちは。"

    return render_template("user_info.html", message=message, username=username)

@app.route("/history")
def history():
    username = session.get("username")

    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT * FROM history WHERE username=%s ORDER BY id DESC", (username,))
    data = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("history.html", history=data)

@app.route("/api/history")
def api_history():
    username = session.get('username')

    if not username:
        return jsonify({"error": "not logged in"}), 401

    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT id, image_path, result, score, timestamp
        FROM history
        WHERE username = %s
        ORDER BY timestamp DESC
    """, (username,))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify(rows)

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
            file.save(f"./uploads/{file.filename}")
        return redirect(url_for("upload"))
    return render_template("upload.html")

@app.route('/')
def index():
    return render_template('index.html')

# === 植物識別 API ===
@app.route('/identify', methods=['POST'])
def identify():
    """植物識別処理（PlantNet + Gemini連携）"""
    try:
        print("\n" + "="*50)
        print("🌱 植物識別プロセス開始")
        print("="*50)
        
        # ステップ1: 画像の確認
        print("\n【ステップ1】画像確認中...")
        if 'image' not in request.files:
            print("❌ 画像がアップロードされていません")
            return jsonify({'error': '画像がアップロードされていません'}), 400
 
        image_file = request.files['image']
        if image_file.filename == '':
            print("❌ 画像が選択されていません")
            return jsonify({'error': '画像が選択されていません'}), 400
        
        print(f"✅ 画像ファイル: {image_file.filename}")
 
        # ステップ2: APIキーの確認
        print("\n【ステップ2】APIキー確認中...")
        if not PLANTNET_API_KEY or PLANTNET_API_KEY == "":
            print("❌ PlantNet APIキーが未設定")
            return jsonify({'error': 'PlantNet APIキーが設定されていません'}), 500
        print("✅ PlantNet APIキー: OK")
        
        if not GEMINI_API_KEY or GEMINI_API_KEY == "":
            print("❌ Gemini APIキーが未設定")
            return jsonify({'error': 'Gemini APIキーが設定されていません'}), 500
        print("✅ Gemini APIキー: OK")
        
        # ステップ3: 画像データの読み込みと保存
        print("\n【ステップ3】画像処理中...")
        image_data = image_file.read()
        print(f"📸 画像サイズ: {len(image_data) / 1024:.1f} KB")
        
        filename = secure_filename(image_file.filename)
        save_path = os.path.join(UPLOAD_FOLDER, filename)

        with open(save_path, "wb") as f:
            f.write(image_data)
        print(f"✅ 画像保存: {save_path}")

        # ステップ4: PlantNet API呼び出し
        print("\n【ステップ4】PlantNet APIで植物識別中...")
        
        # 画像を再度開く（PlantNet APIに送信するため）
        image_file.seek(0)  # ファイルポインタを先頭に戻す
        
        files = {
            'images': (image_file.filename, image_file.stream, image_file.content_type)
        }
        data = {
            'organs': 'auto'  # または 'leaf', 'flower', 'fruit', 'bark'
        }
        
        api_url = f'https://my-api.plantnet.org/v2/identify/all?api-key={PLANTNET_API_KEY}'
        print(f"📡 送信先: {api_url[:60]}...")
        print(f"📡 リクエスト送信中...")

        response = requests.post(
            api_url,
            files=files,
            data=data,
            timeout=30
        )

        print(f"📡 レスポンスコード: {response.status_code}")

        # エラーチェック
        if response.status_code != 200:
            print(f"❌ PlantNet APIエラー")
            print(f"❌ レスポンス: {response.text[:500]}")
            
            error_msg = f'PlantNet APIエラー (コード: {response.status_code})'
            try:
                error_detail = response.json()
                if 'message' in error_detail:
                    error_msg = f"APIエラー: {error_detail['message']}"
                    print(f"❌ エラーメッセージ: {error_detail['message']}")
            except:
                pass
            
            return jsonify({'error': error_msg}), response.status_code

        # PlantNetのレスポンスをパース
        result = response.json()
        print("✅ PlantNet APIレスポンス取得成功")
        
        # レスポンス構造の確認
        if 'results' in result:
            print(f"🔍 識別候補数: {len(result['results'])}件")
        else:
            print("⚠️ 'results'キーが見つかりません")
            print(f"🔍 レスポンスキー: {list(result.keys())}")

        # ステップ5: 識別結果の抽出
        print("\n【ステップ5】識別結果を抽出中...")
        
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        image_url = f"data:{image_file.content_type};base64,{image_base64}"

        top_plant_name = None
        top_score = 0
        top_common_names = []

        if 'results' in result and len(result.get('results', [])) > 0:
            top = result['results'][0]
            
            # 学名の取得
            species = top.get('species', {})
            top_plant_name = species.get('scientificNameWithoutAuthor', species.get('scientificName', '不明'))
            top_score = top.get('score', 0)
            
            # 一般名（日本語名など）の取得
            common_names = species.get('commonNames', [])
            if common_names:
                top_common_names = common_names[:3]  # 上位3つ
            
            print(f"🌿 識別結果: {top_plant_name}")
            print(f"🌿 確信度: {top_score:.1%}")
            if top_common_names:
                print(f"🌿 一般名: {', '.join(top_common_names)}")
        else:
            print("⚠️ 識別結果が見つかりませんでした")
            top_plant_name = None
            top_score = 0

        # ステップ6: Gemini APIで詳細説明を生成
        print("\n【ステップ6】Gemini APIで詳細説明を生成中...")
        
        if top_plant_name:
            try:
                gemini_description = get_gemini_description_enhanced(
                    top_plant_name, 
                    top_common_names
                )
                print("✅ Gemini説明生成成功")
            except Exception as gemini_error:
                print(f"⚠️ Gemini説明生成エラー: {str(gemini_error)}")
                gemini_description = {
                    "花言葉": "情報の取得に失敗しました",
                    "由来": "",
                    "栽培方法": "",
                    "特徴": ""
                }
        else:
            print("⚠️ 植物名が特定できなかったためGemini説明をスキップ")
            gemini_description = {
                "花言葉": "植物名が特定できなかったため説明を生成できませんでした。",
                "由来": "画像の品質を確認するか、別の角度から撮影してみてください。",
                "栽培方法": "葉、花、果実など、特徴的な部分が写っている画像を使用すると精度が上がります。",
                "特徴": ""
            }

        # ステップ7: データベースに保存
        print("\n【ステップ7】データベースに保存中...")
        username = session.get("username")
        
        if username:
            try:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO history (username, image_path, result, score, timestamp)
                    VALUES (%s, %s, %s, %s, %s)
                """, (username, image_url, top_plant_name, top_score, datetime.now()))
                conn.commit()
                cur.close()
                conn.close()
                print("✅ データベース保存成功")
            except Exception as db_error:
                print(f"⚠️ データベース保存エラー: {str(db_error)}")
        else:
            print("⚠️ ユーザーがログインしていないため保存スキップ")

        # ステップ8: レスポンスを返す
        print("\n" + "="*50)
        print("✅ 識別完了")
        print("="*50 + "\n")

        return jsonify({
            'success': True,
            'image_url': image_url,
            'results': result.get('results', []),
            'top_result': {
                'name': top_plant_name,
                'score': top_score,
                'common_names': top_common_names
            },
            'gemini_description': gemini_description
        })

    except requests.exceptions.Timeout:
        print("❌ タイムアウトエラー")
        return jsonify({'error': '通信がタイムアウトしました。もう一度お試しください。'}), 500
    
    except requests.exceptions.ConnectionError:
        print("❌ 接続エラー")
        return jsonify({'error': 'PlantNet APIに接続できませんでした。ネットワーク接続を確認してください。'}), 500
    
    except requests.exceptions.RequestException as req_error:
        print(f"❌ 通信エラー: {str(req_error)}")
        return jsonify({'error': f'通信エラー: {str(req_error)}'}), 500
    
    except Exception as e:
        print(f"❌ 予期しないエラー: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'識別処理エラー: {str(e)}'}), 500


def get_gemini_description_enhanced(plant_name, common_names=None):
    """
    Geminiで植物の詳細説明を生成（改善版）
    
    Args:
        plant_name: 学名
        common_names: 一般名のリスト（オプション）
    """
    try:
        print(f"🤖 Gemini説明生成: {plant_name}")
        
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        # 一般名があれば追加
        common_names_text = ""
        if common_names and len(common_names) > 0:
            common_names_text = f"\n- 一般名: {', '.join(common_names)}"
        
        prompt = f"""
次の植物について日本語で詳しく説明してください。

- 学名: {plant_name}{common_names_text}

以下の項目をそれぞれ「花言葉」「由来」「栽培方法」「特徴」という見出しの下に出力してください。
各項目は2-3文で簡潔に説明してください。

出力フォーマット:
花言葉: （ここに説明）
由来: （ここに説明）
栽培方法: （ここに説明）
特徴: （ここに説明）

重要: マークダウン記法（**、#など）は使用せず、プレーンテキストで出力してください。
"""
        
        print("🤖 Geminiにリクエスト送信...")
        response = model.generate_content(prompt)
        text = response.text
        print(f"🤖 Geminiレスポンス受信 ({len(text)} 文字)")
    
        # レスポンスをパース
        sections = {"花言葉": "", "由来": "", "栽培方法": "", "特徴": ""}
        current_key = None
    
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            
            # マークダウン記号を削除
            clean_line = line.replace("*", "").replace("#", "").replace("-", "").strip()
            is_header_line = False

            for key in sections.keys():
                if clean_line.startswith(key + ":") or clean_line.startswith(key + "："):
                    current_key = key
                    is_header_line = True
                    # ヘッダー行の内容を取得
                    if ":" in clean_line:
                        content = clean_line.split(":", 1)[1]
                    elif "：" in clean_line:
                        content = clean_line.split("：", 1)[1]
                    else:
                        content = ""
                    sections[key] = content.strip()
                    break
            
            # ヘッダー行でない場合、現在のキーに内容を追加
            if not is_header_line and current_key:
                if sections[current_key]:
                    sections[current_key] += "\n" + line
                else:
                    sections[current_key] = line
        
        # 各セクションの内容をトリム
        for key in sections:
            sections[key] = sections[key].strip()
            if not sections[key]:
                sections[key] = "情報がありません"
        
        print("✅ 説明のパース成功")
        return sections

    except Exception as e:
        print(f"❌ Gemini Description Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "花言葉": "情報の取得に失敗しました",
            "由来": f"エラー: {str(e)}",
            "栽培方法": "APIキーまたはネットワーク接続を確認してください",
            "特徴": ""
        }
    
# === 病気・害虫診断 API ===
@app.route('/diagnose', methods=['POST'])
def diagnose():
    """病気・害虫診断処理（Gemini Vision使用）"""
    try:
        if 'image' not in request.files:
            return jsonify({'error': '画像がアップロードされていません'}), 400
 
        image_file = request.files['image']
        if image_file.filename == '':
            return jsonify({'error': '画像が選択されていません'}), 400
 
        image_data = image_file.read()

        filename = secure_filename(image_file.filename)
        save_path = os.path.join(UPLOAD_FOLDER, filename)

        with open(save_path, "wb") as f:
            f.write(image_data)

        # ブラウザ表示用Base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        image_url = f"data:{image_file.content_type};base64,{image_base64}"

        # Gemini Visionで病気・害虫診断（新ロジック呼び出し）
        diagnosis = diagnose_plant_disease(image_data)

        username = session.get("username")
        if username:
            conn = get_connection()
            cur = conn.cursor()

            # DB保存（diagnosisのキーはJSONモードで固定されているため安全）
            cur.execute("""
                INSERT INTO diagnosis_history (username, image_path, health_status, diagnosis, symptoms, solution, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                username, 
                image_url, 
                diagnosis.get("健康状態", "不明"), 
                diagnosis.get("診断結果", "不明"),
                diagnosis.get("症状", ""),
                diagnosis.get("対処法", ""),
                datetime.now()
            ))

            conn.commit()
            cur.close()
            conn.close()

        return jsonify({
            'success': True,
            'image_url': image_url,
            'diagnosis': diagnosis
        })

    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/diagnose-page')
def diagnose_page():
    username = session.get("username")
    if not username:
        return redirect(url_for("login_bp.login"))
    return render_template('diagnose.html')

@app.route("/diagnosis-history")
def diagnosis_history():
    username = session.get("username")
    if not username:
        return redirect(url_for("login_bp.login"))

    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT * FROM diagnosis_history 
        WHERE username=%s 
        ORDER BY timestamp DESC
    """, (username,))
    data = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("diagnosis_history.html", history=data)

@app.route("/api/diagnosis-history")
def api_diagnosis_history():
    username = session.get('username')
    if not username:
        return jsonify({"error": "not logged in"}), 401
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, image_path, health_status, diagnosis, symptoms, solution, timestamp
        FROM diagnosis_history
        WHERE username = %s
        ORDER BY timestamp DESC
    """, (username,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(rows)

@app.route('/result')
def result():
    return render_template('result.html')

@app.route("/test-insert")
def test_insert():
    username = "test_user"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO history (username, image_path, result, score, timestamp)
        VALUES (%s, %s, %s, %s, %s)
    """, (username, "test_image_path", "Test Plant", 0.99, datetime.now()))
    conn.commit()
    cur.close()
    conn.close()
    return "テストデータを追加しました！"

# ==========================================
# ★ 日記・リマインダー機能
# ==========================================

@app.route('/diary')
def diary_list():
    username = session.get("username")
    if not username:
        return redirect(url_for("login_bp.login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    if not user:
        return redirect(url_for("login_bp.login"))
    user_id = user['id']

    cursor.execute("""
        SELECT *, 
        DATEDIFF(NOW(), last_watered) as days_since_water 
        FROM user_plants 
        WHERE user_id = %s 
        ORDER BY created_at DESC
    """, (user_id,))
    plants = cursor.fetchall()
    
    cursor.close()
    conn.close()

    for plant in plants:
        if plant['last_watered']:
            plant['needs_water'] = plant['days_since_water'] >= plant['watering_interval']
        else:
            plant['needs_water'] = True

    return render_template('diary_list.html', plants=plants)

@app.route('/diary/add', methods=['GET', 'POST'])
def add_plant():
    if not session.get("username"):
        return redirect(url_for("login_bp.login"))

    if request.method == 'POST':
        name = request.form.get('name')
        species = request.form.get('species')
        interval = request.form.get('interval')
        image = request.files.get('image')

        image_path = None
        if image and image.filename != '':
            filename = secure_filename(f"plant_{datetime.now().timestamp()}_{image.filename}")
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            image.save(save_path)
            image_path = "/" + save_path

        username = session.get("username")
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        user_id = cursor.fetchone()['id']

        cursor.execute("""
            INSERT INTO user_plants (user_id, name, species, image_path, watering_interval, last_watered)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (user_id, name, species, image_path, interval))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return redirect(url_for('diary_list'))

    return render_template('diary_add.html')

# --- チャットボット用のエンドポイント ---
@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get("message", "")
    context = data.get("context", "") # 現在見ている植物の情報など

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        # 読みやすさを重視した指示を与える
        prompt = f"""
        あなたは植物ケアのアシスタントです。
        ユーザーは画面の文字が小さくて読みづらいと感じている可能性があります。
        
        以下のコンテキスト（現在の状況）を踏まえ、ユーザーの質問に日本語で答えてください。
        回答は「短く」「簡潔に」「箇条書き」を多用し、一目で内容がわかるようにしてください。
        
        状況: {context}
        ユーザーの質問: {user_message}
        """
        
        response = model.generate_content(prompt)
        return jsonify({"reply": response.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/diary/<int:plant_id>', methods=['GET', 'POST'])
def diary_detail(plant_id):
    if not session.get("username"):
        return redirect(url_for("login_bp.login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        log_type = request.form.get('log_type')
        content = request.form.get('content')
        image = request.files.get('image')

        image_path = None
        if image and image.filename != '':
            filename = secure_filename(f"log_{datetime.now().timestamp()}_{image.filename}")
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            image.save(save_path)
            image_path = "/" + save_path

        cursor.execute("""
            INSERT INTO plant_logs (plant_id, log_type, content, image_path, log_date)
            VALUES (%s, %s, %s, %s, NOW())
        """, (plant_id, log_type, content, image_path))

        if log_type == 'water':
            cursor.execute("UPDATE user_plants SET last_watered = NOW() WHERE id = %s", (plant_id,))

        conn.commit()
        return redirect(url_for('diary_detail', plant_id=plant_id))

    cursor.execute("SELECT * FROM user_plants WHERE id = %s", (plant_id,))
    plant = cursor.fetchone()

    cursor.execute("SELECT * FROM plant_logs WHERE plant_id = %s ORDER BY log_date DESC", (plant_id,))
    logs = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('diary_detail.html', plant=plant, logs=logs)

if __name__ == '__main__':
    print('=' * 50)
    print('🚀 PlantNet 植物識別アプリを起動中...')
    print('📍 http://localhost:5001')
    print('=' * 50)
    app.run(debug=True, port=5001, host="127.0.0.1")