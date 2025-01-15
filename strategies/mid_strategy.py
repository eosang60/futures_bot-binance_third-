# futures_bot/strategies/mid_strategy.py

import pandas as pd
import ccxt.async_support as ccxt_async
from ..indicators.ma import ema
from ..indicators.rsi import rsi
from ..indicators.macd import macd
from .common_utils import PositionState
from ..config import (
    MID_LOOKBACK, MID_VOLFILTER,
    MID_PARTIAL_TP_LEVELS, MID_PARTIAL_TP_RATIO,
    MID_STOP_LOSS, MID_TRAIL_STOP
)
from ..utils.telegram_notifier import send_telegram_message

async def fetch_ohlcv_binance(symbol, timeframe, limit=50):
    ex= ccxt_async.binance({"options":{"defaultType":"future"}})
    ex.urls["api"]["fapiPublic"]= "https://fapi.binance.com/fapi/v1"
    data= await ex.fetch_ohlcv(symbol, timeframe, limit=limit)
    await ex.close()
    return data

class MidStrategy:
    """
    중기(15m + 1h) 
    - 1h: ema(20)>ema(60) or macd>0 or recent2 +2%
    - 15m: lookback=15, cp>recentHigh, volume>avgVol*1.3
    - partialTP(5%,10%), stoploss(5%), trail(3%)
    """
    def __init__(self, client, allocated_balance=0.0):
        self.client= client
        self.balance= allocated_balance
        self.positions= {}

    async def run(self, symbol, cp):
        pos= self.positions.setdefault(symbol, PositionState())
        if not pos.in_position:
            cond= await self.check_condition(symbol, cp)
            if cond:
                await self.enter_long(symbol, cp, pos)
        else:
            await self.manage_position(symbol, pos, cp)

    async def check_condition(self, symbol, cp):
        big_ok= await self.check_1h_trend(symbol)
        small_ok= await self.check_15m_breakout(symbol, cp)
        return (big_ok and small_ok)

    async def check_1h_trend(self, symbol):
        data= await fetch_ohlcv_binance(symbol,"1h",limit=60)
        df= pd.DataFrame(data, columns=["ts","open","high","low","close","vol"])
        if len(df)< 20:
            return False
        c= df["close"]
        e20= ema(c,20).iloc[-1]
        e60= ema(c,60).iloc[-1] if len(c)>=60 else e20
        mac= macd(c,fast=12,slow=26,signal=9)
        macd_line= mac["macd_line"].iloc[-1]
        # recent2 +2%
        recent2= c.iloc[-2:]
        change= (recent2.iloc[-1]/recent2.iloc[0]) -1
        if (e20> e60 and macd_line>0) or (change>=0.02):
            return True
        return False

    async def check_15m_breakout(self, symbol, cp):
        data= await fetch_ohlcv_binance(symbol,"15m",limit= MID_LOOKBACK+5)
        df= pd.DataFrame(data, columns=["ts","open","high","low","close","vol"])
        if len(df)< MID_LOOKBACK:
            return False
        hi= df["high"].iloc[-MID_LOOKBACK:].max()
        if cp<= hi:
            return False
        # volume
        last_vol= df["vol"].iloc[-1]
        avg_vol= df["vol"].iloc[-MID_LOOKBACK:].mean()
        if last_vol< avg_vol* MID_VOLFILTER:
            return False
        return True

    async def enter_long(self, symbol, cp, pos: PositionState):
        use= self.balance*0.3
        qty= use/cp
        od= await self.client.create_order(symbol,"buy", qty,"MARKET")
        if od:
            fills= od["info"].get("fills",[])
            tq=0; tc=0
            for f in fills:
                p= float(f["price"]); q= float(f["qty"])
                tq+= q; tc+= p*q
            if tq>0:
                avgp= tc/tq
                pos.in_position= True
                pos.side= "LONG"
                pos.entry_price= avgp
                pos.size= tq
                pos.highest_price= avgp
                send_telegram_message(f"[중기진입]{symbol} @ {avgp} size={tq}")

    async def manage_position(self, symbol, pos: PositionState, cp):
        gain= (cp/ pos.entry_price)-1.0
        # partialTP
        for lv in MID_PARTIAL_TP_LEVELS:
            if gain>= lv and lv not in pos.partial_tp_done:
                partial= pos.size* MID_PARTIAL_TP_RATIO
                od= await self.client.create_order(symbol,"sell", partial,"MARKET")
                if od:
                    pos.size-= partial
                    pos.partial_tp_done.add(lv)
                    send_telegram_message(f"[중기익절]{symbol} lv={lv*100:.1f}% remain={pos.size}")

        # stoploss
        if gain<= -MID_STOP_LOSS:
            od= await self.client.create_order(symbol,"sell", pos.size,"MARKET")
            if od:
                send_telegram_message(f"[중기손절]{symbol} -{MID_STOP_LOSS*100:.1f}%")
                pos.in_position= False
                pos.size= 0.0
                pos.partial_tp_done.clear()

        # trail
        if cp> pos.highest_price:
            pos.highest_price= cp
        if cp<= pos.highest_price*(1- MID_TRAIL_STOP):
            od= await self.client.create_order(symbol,"sell", pos.size,"MARKET")
            if od:
                send_telegram_message(f"[중기트레일]{symbol}")
                pos.in_position= False
                pos.size=0.0
                pos.partial_tp_done.clear()
