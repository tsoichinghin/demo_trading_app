import ccxt
import logging
from decimal import Decimal
from flask import Flask
from flask_socketio import SocketIO
import threading
import csv
import os

# 獲取 binance/ 目錄的絕對路徑
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 初始化設定
TIMEFRAME = '30m' # K線時間圖
INITIAL_CAPITAL = 1000.0 # 起始本金
MIN_TRADE_AMOUNT = 1.0 # 每單最少投資金額
RESULTS_DIR = f"{BASE_DIR}/results"
CSV_FILE = os.path.join(RESULTS_DIR, 'results.csv')
CURRENT_DATE = None

# 初始化交易所
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

with open(CSV_FILE, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Trade Number', 'Direction', 'Symbol', 'Open Time', 'Close Time',
                        'Open Price', 'Close Price', 'Investing Amount', 'Gain', 'Change Percentage', 'Profit Loss Ratio', 'Capital', 'Profit or Loss'])

# Flask 和 SocketIO
app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))
socketio = SocketIO(app)

# 全局變量
thread_id = 0
capital_lock = threading.Lock()
trade_count_lock = threading.Lock()
positions = []
trade_history = []
capital = [Decimal(str(INITIAL_CAPITAL))]
history_capital = [Decimal(str(INITIAL_CAPITAL))]
trade_count = 0
allow_new_threads = True
search_threads_active = 0
price_drop_active = 0
active_lock = threading.Lock()
log_history = []

# 自定義 SocketIOHandler
class SocketIOHandler(logging.Handler):
    def emit(self, record):
        msg = self.format(record)
        if len(log_history) >= 100:
            log_history.pop(0)
        log_history.append(msg)
        try:
            socketio.emit('update_logs', {'log': msg})
        except Exception as e:
            print(f"Error emitting log via SocketIO: {e}")

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('TradingApp')
handler = SocketIOHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(handler)
