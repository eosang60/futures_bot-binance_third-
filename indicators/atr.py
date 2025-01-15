# futures_bot/indicators/atr.py
import pandas as pd
import numpy as np

def atr(df: pd.DataFrame, period=14):
    h= df["high"]
    l= df["low"]
    c= df["close"].shift(1)
    tr1= h-l
    tr2= (h-c).abs()
    tr3= (l-c).abs()
    tr= pd.concat([tr1,tr2,tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()
