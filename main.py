# futures_bot/main.py

import asyncio
import threading
import requests
from .advanced_exchange_client import AdvancedExchangeClient
from .user_data_stream import UserDataStream
from .utils.risk_manager import RiskManager
from .utils.telegram_notifier import send_telegram_message
from .strategies.short_strategy import ShortStrategy
from .strategies.mid_strategy import MidStrategy
from .config import (
    API_KEY, API_SECRET,
    SHORT_SYMBOLS, MID_SYMBOLS,
    SHORT_RATIO, MID_RATIO,
    DEFAULT_LEVERAGE, MARGIN_TYPE,
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
    CIRCUIT_CHECK_INTERVAL
)

class BotRunner:
    def __init__(self):
        self.client= AdvancedExchangeClient()
        self.client.set_api_keys(API_KEY, API_SECRET)
        self.risk_manager= RiskManager(on_circuit_break=self.on_circuit_break)

        self.short_strategy= None
        self.mid_strategy= None

        self.short_bot_on= True
        self.mid_bot_on= True

        self.user_data= UserDataStream(
            api_key= API_KEY,
            on_account_update= self.on_account_update,
            on_order_update= self.on_order_update
        )

        self.running= True
        self._initialized= False

        # 주문 추적
        self.unfilled_orders= {}  # orderId-> { "strategy":"short"/"mid", "symbol":"BTC/USDT", "side":"BUY"/"SELL", "filled":0.0, "origQty":..., "entry":bool }

    async def on_circuit_break(self):
        await self.force_exit_all_positions()
        self.running= False
        send_telegram_message("[서킷브레이커 발동] 전 포지션 청산 명령 -> 대기")

    async def on_account_update(self, event):
        send_telegram_message(f"[ACCOUNT_UPDATE]{event}")

    async def on_order_update(self, event):
        """
        ORDER_TRADE_UPDATE => 부분 체결
        event["o"]={
          "i": orderId,
          "c": clientOrderId,
          "X": PARTIALLY_FILLED / FILLED / NEW / ...
          "z": filledQty,
          "q": origQty,
          "s": 'BTCUSDT',
          "S": 'BUY'/'SELL'
        }
        """
        data= event.get("o", {})
        orderId= data.get("i")
        cId= data.get("c","")
        status= data.get("X","")
        filledQty= float(data.get("z","0.0"))
        origQty= float(data.get("q","0.0"))
        sym= data.get("s","")
        side= data.get("S","BUY")

        if orderId not in self.unfilled_orders:
            # older or not tracked
            return

        rec= self.unfilled_orders[orderId]
        prev_filled= rec.get("filled",0.0)
        delta= filledQty - prev_filled
        rec["filled"]= filledQty
        remain= origQty- filledQty
        strategy_name= rec["strategy"]
        symbol= rec["symbol"]

        # pos update
        if strategy_name=="short":
            pos= self.short_strategy.positions.get(symbol, None)
        else:
            pos= self.mid_strategy.positions.get(symbol, None)

        if pos:
            if side=="BUY":
                pos.size+= delta
            else:
                pos.size-= delta
            if pos.size<1e-9:
                pos.size=0.0
                pos.in_position= False

        if status=="PARTIALLY_FILLED":
            send_telegram_message(f"[ORDER_PARTIAL]{strategy_name} {sym} {orderId} fill={filledQty}/{origQty}, remain={remain}")
        elif status=="FILLED":
            send_telegram_message(f"[ORDER_FILLED]{strategy_name} {sym} {orderId}")
            self.unfilled_orders.pop(orderId, None)

    async def force_exit_all_positions(self):
        # short
        if self.short_strategy:
            for sym, pos in self.short_strategy.positions.items():
                if pos.in_position and pos.size>0:
                    od= await self.client.create_order(sym, "sell", pos.size,"MARKET", None,
                        {"newClientOrderId":f"short_force_{int(asyncio.get_event_loop().time())}"})
                    if od:
                        oId= od["id"]
                        self.unfilled_orders[oId]= {
                            "strategy":"short",
                            "symbol": sym,
                            "side":"SELL",
                            "filled":0.0,
                            "origQty": pos.size,
                            "entry":False
                        }
                    pos.in_position= False
                    pos.size=0.0
        # mid
        if self.mid_strategy:
            for sym, pos in self.mid_strategy.positions.items():
                if pos.in_position and pos.size>0:
                    od= await self.client.create_order(sym, "sell", pos.size,"MARKET", None,
                        {"newClientOrderId":f"mid_force_{int(asyncio.get_event_loop().time())}"})
                    if od:
                        oId= od["id"]
                        self.unfilled_orders[oId]={
                            "strategy":"mid",
                            "symbol": sym,
                            "side":"SELL",
                            "filled":0.0,
                            "origQty": pos.size,
                            "entry":False
                        }
                    pos.in_position= False
                    pos.size=0.0

    async def init_bot(self):
        bal= await self.client.fetch_balance()
        usdt= bal.get("USDT",{}).get("free",0.0)
        self.risk_manager.initial_balance= usdt
        send_telegram_message(f"[BOT INIT] total USDT={usdt}")

        short_bal= usdt* SHORT_RATIO
        mid_bal  = usdt* MID_RATIO

        self.short_strategy= ShortStrategy(self.client, short_bal)
        self.mid_strategy= MidStrategy(self.client, mid_bal)

        # 심볼별 레버리지
        for s in SHORT_SYMBOLS+ MID_SYMBOLS:
            await self.client.init_symbol(s, DEFAULT_LEVERAGE, MARGIN_TYPE)

        asyncio.create_task(self.user_data.start())

        threading.Thread(target=self.telegram_command_listener, daemon=True).start()

        self._initialized= True

    def telegram_command_listener(self):
        import time
        url= f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        offset=0
        while self.running:
            r= requests.get(url+f"?offset={offset+1}&timeout=5")
            if r.status_code==200:
                data= r.json()
                if data["ok"]:
                    results= data["result"]
                    for up in results:
                        offset= up["update_id"]
                        txt= up.get("message",{}).get("text","")
                        chatid= up.get("message",{}).get("chat",{}).get("id","")
                        if str(chatid)== TELEGRAM_CHAT_ID:
                            cmd= txt.strip().lower()
                            if cmd=="/stop":
                                send_telegram_message("[수동정지]/stop")
                                self.running= False
                            elif cmd=="/status":
                                st= "PAUSED" if self.risk_manager.is_paused() else "RUNNING"
                                msg= f"[STATUS]{st}, short_on={self.short_bot_on}, mid_on={self.mid_bot_on}"
                                send_telegram_message(msg)
                            elif cmd=="/shorton":
                                self.short_bot_on= True
                                send_telegram_message("[단타 봇 ON]")
                            elif cmd=="/shortoff":
                                self.short_bot_on= False
                                send_telegram_message("[단타 봇 OFF]")
                            elif cmd=="/midon":
                                self.mid_bot_on= True
                                send_telegram_message("[중기 봇 ON]")
                            elif cmd=="/midoff":
                                self.mid_bot_on= False
                                send_telegram_message("[중기 봇 OFF]")
            time.sleep(2)

    async def run_short_loop(self, sym):
        while self.running:
            if self.risk_manager.is_paused():
                await asyncio.sleep(5)
                continue
            if not self.short_bot_on:
                await asyncio.sleep(5)
                continue
            ticker= await self.client.watch_ticker(sym)
            if ticker:
                cp= float(ticker["last"])
                await self.short_strategy.run(sym, cp)
            await asyncio.sleep(1)

    async def run_mid_loop(self, sym):
        while self.running:
            if self.risk_manager.is_paused():
                await asyncio.sleep(5)
                continue
            if not self.mid_bot_on:
                await asyncio.sleep(5)
                continue
            ticker= await self.client.watch_ticker(sym)
            if ticker:
                cp= float(ticker["last"])
                await self.mid_strategy.run(sym, cp)
            await asyncio.sleep(3)

    async def risk_checker(self):
        while self.running:
            if self.risk_manager.is_paused():
                await asyncio.sleep(5)
                continue
            bal= await self.client.fetch_balance()
            usdt_free= bal.get("USDT",{}).get("free",0.0)
            self.risk_manager.check_drawdown(usdt_free)
            await asyncio.sleep(CIRCUIT_CHECK_INTERVAL)

    async def start(self):
        await self.init_bot()
        tasks= []
        for sym in SHORT_SYMBOLS:
            tasks.append(asyncio.create_task(self.run_short_loop(sym)))
        for sym in MID_SYMBOLS:
            tasks.append(asyncio.create_task(self.run_mid_loop(sym)))
        tasks.append(asyncio.create_task(self.risk_checker()))
        await asyncio.gather(*tasks)

def main():
    runner= BotRunner()
    asyncio.run(runner.start())

if __name__=="__main__":
    main()
