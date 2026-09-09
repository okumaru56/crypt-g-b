import os
import sys
import datetime
import math
import time
import hmac
import hashlib
import json
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 環境変数の取得
API_KEY = os.environ.get('GMO_API_KEY')
SECRET_KEY = os.environ.get('GMO_SECRET_KEY')

SMTP_USER = os.environ.get('SMTP_USER')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
TO_EMAIL = os.environ.get('TO_EMAIL')

PUBLIC_URL = "https://api.coin.z.com/public"
PRIVATE_URL = "https://api.coin.z.com/private"

def send_email(subject, body):
    """メール通知ヘルパー"""
    if not all([SMTP_USER, SMTP_PASSWORD, TO_EMAIL]):
        print("警告: メール設定が不足しているため、メール送信をスキップします。")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = TO_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("メール通知を送信しました。")
    except Exception as e:
        print(f"メール送信に失敗しました: {e}")

def gmo_private_request(method, path, body=None):
    """GMOコイン プライベートAPI認証リクエスト関数"""
    timestamp = str(int(time.time() * 1000))
    body_str = json.dumps(body) if body else ""
    
    text = timestamp + method + path + body_str
    sign = hmac.new(SECRET_KEY.encode('utf-8'), text.encode('utf-8'), hashlib.sha256).hexdigest()

    headers = {
        "API-KEY": API_KEY,
        "API-TIMESTAMP": timestamp,
        "API-SIGN": sign,
        "Content-Type": "application/json"
    }

    url = PRIVATE_URL + path
    if method == "GET":
        res = requests.get(url, headers=headers)
    else:
        res = requests.post(url, headers=headers, data=body_str)
        
    return res.json()

def main():
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    date_str = today.strftime('%Y-%m-%d')
    
    # テスト時等で日付判定をスキップしたい場合は if文をコメントアウトしてください
    if today.day != 1:
        print(f"本日は {date_str} です。積立指定日ではないため終了します。")
        return

    jpy_budget = 3000
    symbol = 'BTC'

    try:
        # 1. 日本円残高確認
        assets_res = gmo_private_request("GET", "/v1/account/assets")
        if assets_res.get("status") != 0:
            raise Exception(f"資産残高の取得に失敗しました: {assets_res}")

        jpy_free = 0
        for asset in assets_res["data"]:
            if asset["symbol"] == "JPY":
                jpy_free = float(asset["amount"])
                break

        print(f"現在のJPY可能残高: {int(jpy_free):,} JPY")

        if jpy_free < jpy_budget:
            error_msg = f"日本円残高が不足しています。\n必要額: {jpy_budget:,} JPY / 残高: {int(jpy_free):,} JPY"
            send_email(f"【失敗】BTC自動積立通知 ({date_str})", f"BTCの自動買付に失敗しました。\n\n理由:\n{error_msg}")
            sys.exit(1)

        # 2. 取引所(現物)最新価格の取得
        ticker_res = requests.get(f"{PUBLIC_URL}/v1/ticker?symbol={symbol}").json()
        if ticker_res.get("status") != 0:
            raise Exception(f"Ticker情報の取得に失敗しました: {ticker_res}")

        last_price = float(ticker_res["data"][0]["last"])
        
        # 0.0001 BTC単位で切り捨て計算
        raw_amount = jpy_budget / last_price
        buy_amount = math.floor(raw_amount * 10000) / 10000

        if buy_amount < 0.0001:
            error_msg = f"購入計算数量({buy_amount} BTC)が最小取引単位(0.0001 BTC)未満です。"
            send_email(f"【失敗】BTC自動積立通知 ({date_str})", f"BTCの自動買付に失敗しました。\n\n理由:\n{error_msg}")
            return

        # 3. 取引所（現物）へ成行買い注文
        order_payload = {
            "symbol": symbol,
            "side": "BUY",
            "executionType": "MARKET",
            "size": str(buy_amount)
        }
        
        order_res = gmo_private_request("POST", "/v1/order", order_payload)
        
        if order_res.get("status") != 0:
            raise Exception(f"注文の送信に失敗しました: {order_res}")

        order_id = order_res.get("data")
        success_body = (
            f"GMOコインでのBTC自動買付が正常に完了しました。\n\n"
            f"----------------------------------------\n"
            f"実行日時: {date_str}\n"
            f"注文ID  : {order_id}\n"
            f"購入金額: 約 {int(buy_amount * last_price):,} 円 ({jpy_budget:,} 円設定)\n"
            f"購入数量: {buy_amount} BTC\n"
            f"適用レート目安: {int(last_price):,} JPY/BTC\n"
            f"----------------------------------------"
        )
        print(success_body)
        send_email(f"【成功】BTC自動積立完了通知 ({date_str})", success_body)

    except Exception as e:
        error_detail = f"処理中に例外が発生しました:\n{str(e)}"
        print(f"エラー: {error_detail}")
        send_email(f"【失敗】BTC自動積立システムエラー ({date_str})", error_detail)
        sys.exit(1)

if __name__ == '__main__':
    main()
