# futures_bot/user_data_stream.py

import asyncio
import requests
import websockets
from .utils.telegram_notifier import send_telegram_message

class UserDataStream:
    def __init__(self, api_key, on_account_update=None, on_order_update=None):
        self.api_key= api_key
        self.on_account_update= on_account_update
        self.on_order_update= on_order_update
        self.listenKey= None
        self.rest_base= "https://fapi.binance.com"
        self.ws_base= "wss://fstream.binance.com"
        self.ws_url= None
        self.closing= False

    def create_listen_key(self):
        url= f"{self.rest_base}/fapi/v1/listenKey"
        headers= {"X-MBX-APIKEY": self.api_key}
        r= requests.post(url, headers=headers)
        if r.status_code==200:
            data= r.json()
            self.listenKey= data["listenKey"]
            self.ws_url= f"{self.ws_base}/stream?streams={self.listenKey}"
            return True
        else:
            send_telegram_message(f"[UserDataStream] listenKey 실패 {r.status_code} {r.text}")
            return False

    def keepalive_listen_key(self):
        url= f"{self.rest_base}/fapi/v1/listenKey"
        headers= {"X-MBX-APIKEY": self.api_key}
        r= requests.put(url, headers=headers)
        if r.status_code!=200:
            send_telegram_message(f"[UserDataStream] keepalive 실패 {r.status_code} {r.text}")

    async def start(self):
        self.closing= False
        while not self.closing:
            ok= self.create_listen_key()
            if not ok:
                break
            await self.run_ws()
            if not self.closing:
                send_telegram_message("[UserDataStream] 재연결 대기5초")
                await asyncio.sleep(5)

    async def run_ws(self):
        send_telegram_message("[UserDataStream] 연결 시도")
        try:
            async with websockets.connect(self.ws_url) as ws:
                send_telegram_message("[UserDataStream] 연결 성공")
                keepalive_task= asyncio.create_task(self.keepalive_loop())
                while not self.closing:
                    msg= await ws.recv()
                    await self.on_message(msg)
                keepalive_task.cancel()
        except Exception as e:
            send_telegram_message(f"[UserDataStream 연결오류]{e}")

    async def on_message(self, msg):
        import json
        data= json.loads(msg)
        event= data.get("data", {})
        etype= event.get("e")
        if etype=="ACCOUNT_UPDATE":
            if self.on_account_update:
                await self.on_account_update(event)
        elif etype=="ORDER_TRADE_UPDATE":
            if self.on_order_update:
                await self.on_order_update(event)

    async def keepalive_loop(self):
        while not self.closing:
            await asyncio.sleep(30*60)
            self.keepalive_listen_key()
            send_telegram_message("[UserDataStream] keepalive 완료")

    def stop(self):
        self.closing= True
