# futures_bot/utils/risk_manager.py
import asyncio
from ..config import MAX_DRAWDOWN_PCT
from .telegram_notifier import send_telegram_message

class RiskManager:
    def __init__(self, on_circuit_break=None):
        self.initial_balance= 0.0
        self.bot_paused= False
        self.on_circuit_break= on_circuit_break

    def check_drawdown(self, current_balance):
        if self.bot_paused:
            return True
        if self.initial_balance<=0:
            return False
        dd_ratio= 1-(current_balance/self.initial_balance)
        if dd_ratio>= MAX_DRAWDOWN_PCT:
            send_telegram_message(f"[서킷브레이커] 손실률={dd_ratio*100:.1f}%->중단")
            self.bot_paused= True
            if self.on_circuit_break:
                asyncio.get_event_loop().create_task(self.on_circuit_break())
            return True
        return False

    def is_paused(self):
        return self.bot_paused
