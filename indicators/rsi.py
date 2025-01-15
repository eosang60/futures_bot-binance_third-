# futures_bot/indicators/rsi.py
import pandas as pd
import numpy as np

def rsi(series: pd.Series, period=14):
    delta= series.diff()
    gain= np.where(delta>0, delta,0)
    loss= np.where(delta<0, -delta,0)
    gain_ema= pd.Series(gain).ewm(span=period).mean()
    loss_ema= pd.Series(loss).ewm(span=period).mean()
    rs= gain_ema/(loss_ema+1e-9)
    return 100- (100/(1+ rs))
