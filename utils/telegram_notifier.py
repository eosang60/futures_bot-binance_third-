# futures_bot/utils/telegram_notifier.py
import requests
from ..config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def send_telegram_message(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[텔레그램미설정]:", msg)
        return
    url= f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload= {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        r= requests.post(url, json=payload)
        if r.status_code!=200:
            print("[텔레그램오류]", r.text)
    except Exception as e:
        print("[텔레그램예외]", e)
