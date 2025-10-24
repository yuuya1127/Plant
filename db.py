import mysql.connector

def get_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",          # ← あなたのMySQLユーザー名
        password="",          # ← あなたのMySQLパスワード
        database="Plant"      # ← 使用するデータベース名
    )
    return conn
