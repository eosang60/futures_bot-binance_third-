# futures_bot/strategies/common_utils.py

class PositionState:
    def __init__(self):
        self.in_position= False
        self.side= None
        self.entry_price= 0.0
        self.size= 0.0
        self.highest_price=0.0
        self.lowest_price=999999.0
        self.partial_tp_done= set()
        self.added_pyramid_levels= set()
