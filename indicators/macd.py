# futures_bot/indicators/macd.py
import pandas as pd

def macd(series: pd.Series, fast=12, slow=26, signal=9):
    emafast= series.ewm(span=fast).mean()
    emaslow= series.ewm(span=slow).mean()
    macd_line= emafast - emaslow
    signal_line= macd_line.ewm(span=signal).mean()
    hist= macd_line - signal_line
    return pd.DataFrame({
        "macd_line": macd_line,
        "signal_line": signal_line,
        "hist": hist
    })
