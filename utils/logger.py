# futures_bot/utils/logger.py
import csv
from datetime import datetime

LOG_FILE= "futures_bot_log.csv"

def log_to_csv(event_type, symbol, price, qty, extra=""):
    now= datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE,"a", newline="", encoding="utf-8") as f:
        writer= csv.writer(f)
        writer.writerow([now, event_type, symbol, price, qty, extra])
