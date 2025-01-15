# futures_bot/config.py

###############################################################################
# 1) 바이낸스 선물 계정 정보 (API 키, 시크릿)
###############################################################################
API_KEY = "L9zZsKFmmAE6AmaPShTt99qOUzDO31T6TEmaCuF0y5cJDyTvEu3gQYO9hlZiuM5f"
API_SECRET = "Wz8WTbIklQazsj1GKy0q4YrSVYdxu4D21Ay1wVnqD9zzKynW9nHc0sg2vZtoGjsg"

###############################################################################
# 2) 텔레그램 설정
###############################################################################
TELEGRAM_TOKEN = "7925352395:AAFb-7Ax2a4L6MHHKh4mRGAhztQ3Ek_Jyp4"      # 텔레그램 봇 토큰 (없으면 "")
TELEGRAM_CHAT_ID = "7718934449"    # 챗 ID (없으면 "")

DEFAULT_LEVERAGE = 10
MARGIN_TYPE = "ISOLATED"

# 심볼
SHORT_SYMBOLS = ["BTC/USDT"]   # 단타
MID_SYMBOLS   = ["ETH/USDT"]   # 중기

# 자금 배분
SHORT_RATIO = 0.35
MID_RATIO   = 0.45
# 나머지 0.20 비상금

# 서킷브레이커
MAX_DRAWDOWN_PCT = 0.50
CIRCUIT_CHECK_INTERVAL = 30

# 중기 파라미터
MID_LOOKBACK = 15
MID_VOLFILTER= 1.3
MID_PARTIAL_TP_LEVELS= [0.05, 0.10]
MID_PARTIAL_TP_RATIO= 0.3
MID_STOP_LOSS= 0.05
MID_TRAIL_STOP= 0.03

# 단타 파라미터
SHORT_TIMEFRAME= "3m"
SHORT_LOOKBACK= 10
SHORT_VOLFILTER= 1.3
SHORT_TICK_MOMENTUM= 2.0
SHORT_PARTIAL_TP_LEVELS= [0.02, 0.04]
SHORT_PARTIAL_TP_RATIO= 0.3
SHORT_STOP_LOSS= 0.015
SHORT_PYRAMID_LEVELS= [0.01, 0.02]
SHORT_PYRAMID_SIZE= 0.5