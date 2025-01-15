# futures_bot/advanced_exchange_client.py

import asyncio
import ccxt.pro as ccxtpro
from ccxt.base.errors import (
    NetworkError, RateLimitExceeded, AuthenticationError,
    InsufficientFunds, ExchangeError, InvalidOrder
)
from .utils.telegram_notifier import send_telegram_message
import time

class AdvancedExchangeClient:
    """
    - Binance 선물 실거래
    - ccxt.pro로 WebSocket ticker
    - 주문 시 재시도 로직 간단 구현
    """
    def __init__(self):
        self.exchange = ccxtpro.binance({
            "enableRateLimit": True,
            "apiKey": "L9zZsKFmmAE6AmaPShTt99qOUzDO31T6TEmaCuF0y5cJDyTvEu3gQYO9hlZiuM5f",  # 아래 set_api_keys 메서드에서 설정
            "secret": "Wz8WTbIklQazsj1GKy0q4YrSVYdxu4D21Ay1wVnqD9zzKynW9nHc0sg2vZtoGjsg",
            "options": {"defaultType": "future"}
        })
        self.max_retries = 3

    def set_api_keys(self, api_key, api_secret):
        self.exchange.apiKey= api_key
        self.exchange.secret= api_secret
        # 실거래 도메인
        self.exchange.urls["api"]["fapiPublic"]  = "https://fapi.binance.com/fapi/v1"
        self.exchange.urls["api"]["fapiPrivate"] = "https://fapi.binance.com/fapi/v1"
        self.exchange.urls["api"]["fapiPrivateV2"]="https://fapi.binance.com/fapi/v2"

    async def init_symbol(self, symbol, leverage=10, margin_type="ISOLATED"):
        sym= symbol.replace("/","")
        try:
            await self.exchange.fapiPrivatePostMarginType({"symbol": sym,"marginType": margin_type})
        except Exception as e:
            send_telegram_message(f"[마진타입 실패]{symbol} {e}")
        try:
            await self.exchange.fapiPrivatePostLeverage({"symbol": sym,"leverage": leverage})
        except Exception as e:
            send_telegram_message(f"[레버리지 실패]{symbol} {e}")

    async def create_order(self, symbol, side, amount, order_type="MARKET", price=None, params=None):
        """
        params={"timeInForce":"IOC"/"FOK"} 등 가능
        """
        if params is None:
            params= {}
        for attempt in range(self.max_retries):
            try:
                if order_type.upper()=="MARKET":
                    return await self.exchange.create_order(symbol, "market", side, amount, None, params)
                elif order_type.upper()=="LIMIT" and price is not None:
                    return await self.exchange.create_order(symbol, "limit", side, amount, price, params)
                else:
                    raise InvalidOrder("주문타입 오류 or price누락")
            except (NetworkError, RateLimitExceeded) as e:
                if attempt< self.max_retries-1:
                    await asyncio.sleep(2+ attempt*2)
                else:
                    send_telegram_message(f"[주문실패]{symbol} {e}")
                    return None
            except (InsufficientFunds, AuthenticationError, ExchangeError) as e:
                send_telegram_message(f"[주문오류]{symbol} {e}")
                return None
        return None

    async def fetch_balance(self):
        for attempt in range(self.max_retries):
            try:
                bal= await self.exchange.fetch_balance()
                return bal
            except (NetworkError, RateLimitExceeded) as e:
                if attempt< self.max_retries-1:
                    await asyncio.sleep(2+attempt*2)
                else:
                    send_telegram_message(f"[잔고조회실패]{e}")
                    return {}
            except Exception as e:
                send_telegram_message(f"[잔고조회오류]{e}")
                return {}
        return {}

    async def watch_ticker(self, symbol):
        for attempt in range(self.max_retries):
            try:
                t= await self.exchange.watch_ticker(symbol)
                return t
            except (NetworkError, RateLimitExceeded) as e:
                if attempt< self.max_retries-1:
                    await asyncio.sleep(2+attempt*2)
                else:
                    send_telegram_message(f"[WS ticker실패]{symbol} {e}")
                    return None
            except Exception as e:
                send_telegram_message(f"[WS ticker오류]{symbol} {e}")
                return None
        return None

    async def watch_trades(self, symbol):
        for attempt in range(self.max_retries):
            try:
                trades= await self.exchange.watch_trades(symbol)
                return trades
            except (NetworkError, RateLimitExceeded) as e:
                if attempt< self.max_retries-1:
                    await asyncio.sleep(2+attempt*2)
                else:
                    send_telegram_message(f"[WS trades실패]{symbol} {e}")
                    return []
            except Exception as e:
                send_telegram_message(f"[WS trades오류]{symbol} {e}")
                return []
        return []