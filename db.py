import mysql.connector

def get_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",          # ← あなたのMySQLユーザー名
        password="",  # ← あなたのMySQLパスワード
        database="Plant"    # ← 上で作ったデータベース名
    )
    return conn