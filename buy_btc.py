import os
import sys
import datetime
import math
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import ccxt

# 環境変数からキーやメール設定を取得
API_KEY = os.environ.get('GMO_API_KEY')
SECRET_KEY = os.environ.get('GMO_SECRET_KEY')

SMTP_USER = os.environ.get('SMTP_USER')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
TO_EMAIL = os.environ.get('TO_EMAIL')

def send_email(subject, body):
    """メールを送信するヘルパー関数"""
    if not all([SMTP_USER, SMTP_PASSWORD, TO_EMAIL]):
        print("警告: メール設定(SMTP_USER, SMTP_PASSWORD, TO_EMAIL)が不足しているため、メール送信をスキップします。")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = TO_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # GmailのSMTPサーバー設定 (Port 587 / STARTTLS)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("メール通知を送信しました。")
    except Exception as e:
        print(f"メール送信に失敗しました: {e}")

# GMOコイン APIの初期化
exchange = ccxt.gmocoin({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
})

def main():
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))) # JST換算
    
    # 毎月1日以外は処理をスキップ（通知も出さずに終了）
    if today.day != 1:
        print(f"本日は {today.strftime('%Y-%m-%d')} です。購入指定日ではないため終了します。")
        return

    date_str = today.strftime('%Y-%m-%d')
    jpy_budget = 3000
    symbol = 'BTC/JPY'

    try:
        # 日本円残高確認
        balance = exchange.fetch_balance()
        jpy_free = balance['free'].get('JPY', 0)

        if jpy_free < jpy_budget:
            error_msg = f"日本円残高が不足しています。\n必要額: {jpy_budget:,} JPY / 現在の残高: {int(jpy_free):,} JPY"
            print(f"エラー: {error_msg}")
            
            # 残高不足通知（失敗）
            send_email(
                subject=f"【失敗】BTC自動積立通知 ({date_str})",
                body=f"BTCの自動買付に失敗しました。\n\n理由: 残高不足\n{error_msg}"
            )
            sys.exit(1)

        # 最新価格取得と数量計算
        ticker = exchange.fetch_ticker(symbol)
        last_price = ticker['last']
        
        raw_amount = jpy_budget / last_price
        buy_amount = math.floor(raw_amount * 10000) / 10000

        if buy_amount < 0.0001:
            error_msg = f"購入計算数量({buy_amount} BTC)が最小取引単位(0.0001 BTC)未満です。"
            print(f"エラー: {error_msg}")
            
            send_email(
                subject=f"【失敗】BTC自動積立通知 ({date_str})",
                body=f"BTCの自動買付に失敗しました。\n\n理由:\n{error_msg}"
            )
            return

        # 取引所（板）へ成行買い注文
        order = exchange.create_order(
            symbol=symbol,
            type='market',
            side='buy',
            amount=buy_amount,
            params={'executionType': 'MARKET'}
        )
        
        # 成功通知メールの本文作成
        success_body = (
            f"GMOコインでのBTC自動買付が正常に完了しました。\n\n"
            f"----------------------------------------\n"
            f"実行日時: {date_str}\n"
            f"注文ID  : {order['id']}\n"
            f"購入金額: 約 {int(buy_amount * last_price):,} 円 ({jpy_budget:,} 円設定)\n"
            f"購入数量: {buy_amount} BTC\n"
            f"適用レート目安: {int(last_price):,} JPY/BTC\n"
            f"----------------------------------------"
        )
        print(success_body)
        
        # 成功メール送信
        send_email(
            subject=f"【成功】BTC自動積立完了通知 ({date_str})",
            body=success_body
        )

    except Exception as e:
        error_detail = f"処理中に予期せぬ例外が発生しました:\n{str(e)}"
        print(f"エラー: {error_detail}")
        
        # 例外エラー通知（失敗）
        send_email(
            subject=f"【失敗】BTC自動積立システムエラー ({date_str})",
            body=f"BTC自動積立スクリプトの実行中にエラーが発生しました。\n\n詳細:\n{error_detail}"
        )
        sys.exit(1)

if __name__ == '__main__':
    main()
