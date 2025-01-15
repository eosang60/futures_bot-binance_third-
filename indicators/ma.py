# futures_bot/indicators/ma.py
import pandas as pd

def ema(series: pd.Series, period=20):
    return series.ewm(span=period, adjust=False).mean()
