from flask import render_template
from .config import app, socketio, positions, capital, trade_history, allow_new_threads, logger, thread_id, search_threads_active, price_drop_active, active_lock, log_history
from .trading_logic import calculate_total_value, deep_copy_positions, trade_searcher
from .trading_logic import decimal_to_str
import threading

@app.route('/')
def positions_page():
    total_positions = len(positions)
    return render_template('positions.html', 
                         positions=positions, 
                         capital=capital, 
                         total_value=calculate_total_value(),
                         total_positions=total_positions)

@app.route('/history')
@app.route('/history/<int:page>')
def history_page(page=1):
    per_page = 50
    total_trades = len(trade_history)
    total_pages = (total_trades + per_page - 1) // per_page
    page = max(1, min(page, total_pages))
    trade_history_copy = trade_history.copy()
    pages = {}
    if total_pages > 1:
        for current_page in range(total_pages, 1, -1):
            page_trades_temporary = []
            page_trades = []
            for _ in range(per_page):
                min_trade = min(trade_history_copy, key=lambda x: x['trade_number'])
                page_trades_temporary.append(min_trade)
                trade_history_copy.remove(min_trade)
            while page_trades_temporary:
                max_trade = max(page_trades_temporary, key=lambda x: x['trade_number'])
                page_trades.append(max_trade)
                page_trades_temporary.remove(max_trade)
            pages[current_page] = page_trades
    if trade_history_copy:
        page_trades_temporary = []
        page_trades = []
        remaining_trades = len(trade_history_copy)
        for _ in range(remaining_trades):
            min_trade = min(trade_history_copy, key=lambda x: x['trade_number'])
            page_trades_temporary.append(min_trade)
            trade_history_copy.remove(min_trade)
        while page_trades_temporary:
            max_trade = max(page_trades_temporary, key=lambda x: x['trade_number'])
            page_trades.append(max_trade)
            page_trades_temporary.remove(max_trade)
        pages[1] = page_trades
    page_trades = pages.get(page, [])
    return render_template('history.html', 
                         trade_history=page_trades, 
                         current_page=page, 
                         total_pages=total_pages, 
                         total_trades=total_trades)

@app.route('/toggle_search', methods=['POST'])
def toggle_search():
    global allow_new_threads, search_threads_active, price_drop_active
    allow_new_threads = not allow_new_threads
    status = 'enabled' if allow_new_threads else 'disabled'
    socketio.emit('update_search_status', {'status': status})
    with active_lock:
        if search_threads_active == 0:
            new_thread_id = thread_id + 1
            threading.Thread(target=trade_searcher, args=(new_thread_id,), daemon=True).start()
        elif search_threads_active == 1 and price_drop_active > 0:
            new_thread_id = thread_id + 1
            threading.Thread(target=trade_searcher, args=(new_thread_id,), daemon=True).start()
    return {'status': status}, 200

@socketio.on('connect')
def handle_connect(auth=None):
    total_positions = len(positions)
    positions_copy = deep_copy_positions(positions)
    capital_copy = f"{capital:.2f}"
    total_value_copy = f"{calculate_total_value():.2f}"
    status = 'enabled' if allow_new_threads else 'disabled'
    total_trades = len(trade_history)
    win_trades = sum(1 for trade in trade_history if trade['profit_or_loss'] == 'profit')
    win_rate = "{:.2f}".format((win_trades / total_trades * 100) if total_trades > 0 else 0)
    socketio.emit('update_positions', {
        'positions': positions_copy,
        'capital': capital_copy,
        'total_value': total_value_copy,
        'search_status': status,
        'win_rate': win_rate,
        'total_trades': total_trades,
        'win_trades': win_trades,
        'total_positions': total_positions
    })
    for log in log_history:
        socketio.emit('update_logs', {'log': log})

@app.route('/logs')
def logs_page():
    return render_template('logs.html')
