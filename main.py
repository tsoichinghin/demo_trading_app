import threading
from app.config import config, logger, socketio, app
from app.trading_logic import trade_searcher
from app import web_interface

if __name__ == '__main__':
    config['thread_id'] += 1
    logger.info("交易程式開啟")
    threading.Thread(target=trade_searcher, args=(), daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=8888, debug=False)
