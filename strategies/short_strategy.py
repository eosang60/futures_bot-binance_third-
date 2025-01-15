# futures_bot/strategies/short_strategy.py

import pandas as pd
import time
import ccxt.async_support as ccxt_async
from .common_utils import PositionState
from ..indicators.ma import ema
from ..indicators.rsi import rsi
from ..indicators.macd import macd
from ..config import (
    SHORT_TIMEFRAME, SHORT_LOOKBACK, SHORT_VOLFILTER,
    SHORT_TICK_MOMENTUM,
    SHORT_PARTIAL_TP_LEVELS, SHORT_PARTIAL_TP_RATIO,
    SHORT_STOP_LOSS, SHORT_PYRAMID_LEVELS, SHORT_PYRAMID_SIZE
)
from ..utils.telegram_notifier import send_telegram_message

async def fetch_ohlcv_binance(symbol, timeframe, limit=50):
    ex= ccxt_async.binance({"options":{"defaultType":"future"}})
    ex.urls["api"]["fapiPublic"]= "https://fapi.binance.com/fapi/v1"
    data= await ex.fetch_ohlcv(symbol, timeframe, limit=limit)
    await ex.close()
    return data

class ShortStrategy:
    """
    단타(3m), 15m 보조(MTF), EMA/RSI/볼륨 + 체결량스파이크,
    부분익절+피라미딩+손절
    """
    def __init__(self, client, allocated_balance=0.0):
        self.client= client
        self.balance= allocated_balance
        self.positions= {}
        self.avg_tick_vol= {}

    async def run(self, symbol, current_price):
        pos= self.positions.setdefault(symbol, PositionState())
        if not pos.in_position:
            ok= await self.check_entry(symbol, current_price)
            if ok:
                await self.enter_long(symbol, current_price, pos)
        else:
            await self.manage_position(symbol, pos, current_price)

    async def check_entry(self, symbol, cp):
        # 15m trend
        big_ok= await self.check_15m_trend(symbol)
        if not big_ok: return False
        # 3m breakout + volume
        brk_ok= await self.check_3m_breakout(symbol, cp)
        if not brk_ok: return False
        # RSI
        data_3= await fetch_ohlcv_binance(symbol, SHORT_TIMEFRAME, limit=35)
        df_3= pd.DataFrame(data_3, columns=["ts","open","high","low","close","vol"])
        rsi_val= rsi(df_3["close"],14).iloc[-1]
        if rsi_val>=70:
            return False
        # tick momentum
        tick_ok= await self.check_tick_momentum(symbol)
        if not tick_ok:
            return False
        return True

    async def check_15m_trend(self, symbol):
        data_15= await fetch_ohlcv_binance(symbol,"15m", limit=60)
        df= pd.DataFrame(data_15, columns=["ts","open","high","low","close","vol"])
        if len(df)<60:
            return False
        c= df["close"]
        e20= ema(c,20).iloc[-1]
        e60= ema(c,60).iloc[-1]
        # rsi(15)
        rsi15= rsi(c,14).iloc[-1]
        # recent2 +2% ?
        recent2= c.iloc[-2:]
        change= (recent2.iloc[-1]/ recent2.iloc[0]) -1
        if (e20> e60 and rsi15<70) or (change>=0.02):
            return True
        return False

    async def check_3m_breakout(self, symbol, cp):
        data_3= await fetch_ohlcv_binance(symbol, SHORT_TIMEFRAME, limit= SHORT_LOOKBACK+5)
        df= pd.DataFrame(data_3, columns=["ts","open","high","low","close","vol"])
        if len(df)< SHORT_LOOKBACK:
            return False
        rh= df["high"].iloc[-SHORT_LOOKBACK:].max()
        if cp<= rh:
            return False
        # volume filter
        last_vol= df["vol"].iloc[-1]
        avg_vol= df["vol"].iloc[-SHORT_LOOKBACK:].mean()
        if last_vol< avg_vol* SHORT_VOLFILTER:
            return False
        return True

    async def check_tick_momentum(self, symbol):
        trades= await self.client.watch_trades(symbol)
        if not trades:
            return False
        import time
        now= time.time()*1000
        window= 30_000
        recent_vol=0
        for t in trades[::-1]:
            if (now - t["timestamp"])<= window:
                recent_vol+= t["amount"]
            else:
                break
        avgv= self.avg_tick_vol.get(symbol,0.0)
        if avgv<1e-9:
            self.avg_tick_vol[symbol]= recent_vol
            return False
        ratio= recent_vol/(avgv+1e-9)
        self.avg_tick_vol[symbol]= avgv*0.8 + recent_vol*0.2
        if ratio>= SHORT_TICK_MOMENTUM:
            return True
        return False

    async def enter_long(self, symbol, cp, pos: PositionState):
        use= self.balance*0.1
        qty= use/cp
        od= await self.client.create_order(symbol,"buy", qty, "MARKET")
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
                send_telegram_message(f"[단타진입]{symbol} @ {avgp}")

    async def manage_position(self, symbol, pos: PositionState, cp):
        gain= (cp/pos.entry_price)-1.0
        # partial tp
        for lv in SHORT_PARTIAL_TP_LEVELS:
            if gain>= lv and lv not in pos.partial_tp_done:
                partial= pos.size* SHORT_PARTIAL_TP_RATIO
                od= await self.client.create_order(symbol,"sell", partial,"MARKET")
                if od:
                    pos.partial_tp_done.add(lv)
                    send_telegram_message(f"[단타익절]{symbol} lv={lv*100:.1f}%, remain={pos.size-partial}")
        # pyramid
        for lv in SHORT_PYRAMID_LEVELS:
            if gain>= lv and lv not in pos.added_pyramid_levels:
                add_qty= pos.size* SHORT_PYRAMID_SIZE
                od= await self.client.create_order(symbol,"buy", add_qty,"MARKET")
                if od:
                    pos.added_pyramid_levels.add(lv)
                    send_telegram_message(f"[단타피라미딩]{symbol} lv={lv*100:.1f}% +{add_qty}")
        # stoploss
        if gain<= -SHORT_STOP_LOSS:
            od= await self.client.create_order(symbol,"sell", pos.size,"MARKET")
            if od:
                send_telegram_message(f"[단타손절]{symbol} -{SHORT_STOP_LOSS*100:.1f}%")
                pos.in_position= False
                pos.size=0.0
                pos.partial_tp_done.clear()
                pos.added_pyramid_levels.clear()

        if cp> pos.highest_price:
            pos.highest_price= cp
