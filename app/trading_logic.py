import threading
import ccxt
import re
import time
import pytz
from datetime import datetime, timedelta
import csv
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
import traceback
from .config import (positions, capital, trade_history, trade_count, allow_new_threads,
                   search_threads_active, active_lock, capital_lock, trade_count_lock,
                   history_capital, MIN_TRADE_AMOUNT, CSV_FILE, socketio, logger, exchange)
from .exchange_utils import get_historical_data, calculate_indicators, check_conditions, get_trade_amount, tp_and_sl
from .market_scanner import scan_markets

def decimal_to_str(data):
    if isinstance(data, Decimal):
        return str(data)
    elif isinstance(data, dict):
        return {k: decimal_to_str(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [decimal_to_str(item) for item in data]
    else:
        return data

def deep_copy_positions(positions):
    return [decimal_to_str(pos.copy()) for pos in positions]

def monitor_position(position):
    global positions, capital
    symbol = position['symbol']
    logger.info(f"線程{position['thread_id']}: 成功開啟 {symbol} 交易")
    while True:
        try:
            df = get_historical_data(symbol, 1)
            current_price = Decimal(str(df['close'].iloc[-1]))
            position['current_price'] = current_price
            total_positions = len(positions)
            positions_copy = deep_copy_positions(positions)
            capital_copy = capital[0]
            capital_copy = Decimal(str(capital_copy))
            capital_copy = f"{capital_copy:.2f}"
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
            if current_price >= position['take_profit']:
                close_position(position, '止盈', position['take_profit'], position['thread_id'])
                break
            elif current_price <= position['stop_loss']:
                close_position(position, '止損', current_price, position['thread_id'])
                break
            time.sleep(1)
        except Exception as e:
            logger.info(f"線程{position['thread_id']}: 維護{symbol}交易時發生錯誤: {e}")

def close_position(position, reason, excute_price, thread_id):
    global capital, trade_count, history_capital
    with capital_lock:
        if reason == '止損':
            crypto_amount = position['amount'] / position['entry_price']
            crypto_amount_after_fee = crypto_amount * Decimal("0.999")
            after_exit_usdt_amount = crypto_amount_after_fee * excute_price
            after_exit_usdt_amount_after_fee = after_exit_usdt_amount * Decimal("0.999")
            pnl = after_exit_usdt_amount_after_fee - position['amount']
            capital[0] = capital[0] + position['amount'] + pnl
            change_percentage = abs(pnl) / position['amount'] * 100
            if pnl < 0:
                change_percentage = -change_percentage
        elif reason == '止盈':
            crypto_amount = position['amount'] / position['entry_price']
            crypto_amount_after_fee = crypto_amount * Decimal("0.999")
            after_exit_usdt_amount = crypto_amount_after_fee * excute_price
            after_exit_usdt_amount_after_fee = after_exit_usdt_amount * Decimal("0.999")
            pnl = after_exit_usdt_amount_after_fee - position['amount']
            capital[0] = capital[0] + position['amount'] + pnl
            change_percentage = abs(pnl) / position['amount'] * 100
        change_percentage = Decimal("{:.2f}".format(change_percentage))
    with trade_count_lock:
        trade_count += 1
        positions.remove(position)
        history_capital[0] = history_capital[0] + pnl
        trade_history.append({
            'trade_number': trade_count,
            'direction': 'LONG',
            'close_reason': reason,
            'symbol': position['symbol'],
            'open_time': position['entry_time'],
            'close_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'open_price': position['entry_price'],
            'close_price': excute_price,
            'investing_amount': position['amount'],
            'gain': pnl,
            'change_percentage': f"{change_percentage}%",
            'profit_loss_ratio': position['profit_loss_ratio'],
            'capital': history_capital[0],
            'profit_or_loss': 'profit' if pnl > 0 else 'loss'
        })
        with open(CSV_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([trade_count, 'LONG', position['symbol'], position['entry_time'],
                             datetime.now().strftime('%Y-%m-%d %H:%M:%S'), position['entry_price'], excute_price,
                             position['amount'], pnl, f"{change_percentage}%", position['profit_loss_ratio'],
                             history_capital[0], 'profit' if pnl > 0 else 'loss'])
    total_trades = len(trade_history)
    win_trades = sum(1 for trade in trade_history if trade['profit_or_loss'] == 'profit')
    win_rate = "{:.2f}".format((win_trades / total_trades * 100) if total_trades > 0 else 0)
    total_positions = len(positions)
    positions_copy = deep_copy_positions(positions)
    capital_copy = capital[0]
    capital_copy = Decimal(str(capital_copy))
    capital_copy = f"{capital_copy:.2f}"
    total_value_copy = f"{calculate_total_value():.2f}"
    status = 'enabled' if allow_new_threads else 'disabled'
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
    logger.info(f"線程{thread_id}: {position['symbol']} 已成功平倉，原因：{reason}")

def calculate_total_value():
    total = capital[0]
    for pos in positions:
        total += pos['current_price'] * (pos['amount'] / pos['entry_price'])
    return total

def trade_searcher(thread_id):
    global capital, allow_new_threads, search_threads_active, CURRENT_DATE
    if thread_id == 1:
        time.sleep(5)
    with active_lock:
        search_threads_active += 1
    class ExitLoopException(Exception):
        pass
    class NextSymbolCheck(Exception):
        pass
    try:
        if allow_new_threads:
            logger.info(f"線程{thread_id}: 准許開啟新線程，開始進入市場掃描")
            utc_tz = pytz.UTC
            CURRENT_DATE = datetime.now(utc_tz).date()
            closing_symbols = scan_markets(CURRENT_DATE)
            markets = exchange.fetch_markets()
            symbols = [market['symbol'] for market in markets if '/USDT' in market['symbol'] and ':USDT' not in market['symbol'] and market['active']]
            pattern = r'(\w*USD\w*/USDT|\w*/USD/USDT)'
            symbols = [symbol for symbol in symbols if not re.search(pattern, symbol)]
            symbols = [symbol for symbol in symbols if symbol not in closing_symbols]
            round = 1
            logger.info(f"線程{thread_id}: 完成讀取市場，開始尋找交易機會")
            while True:
                for symbol in symbols:
                    if symbol not in [pos['symbol'] for pos in positions]:
                        current_time = datetime.now()
                        thirty_minutes_ago = current_time - timedelta(minutes=30)
                        has_recent_trade = any(
                            trade['symbol'] == symbol and 
                            datetime.strptime(trade['open_time'], '%Y-%m-%d %H:%M:%S') >= thirty_minutes_ago
                            for trade in trade_history
                        )
                        if has_recent_trade:
                            logger.info(f"線程{thread_id}: {symbol} 在過去 30 分鐘內曾開過單，跳過")
                            continue
                        try:
                            df = get_historical_data(symbol, 340)
                            if len(df) < 340:
                                continue
                            df = calculate_indicators(df)
                            if check_conditions(df):
                                process_trade = False
                                with capital_lock:
                                    if capital[0] >= Decimal(str(MIN_TRADE_AMOUNT)):
                                        logger.info(f"線程{thread_id}: 找到可能交易機會 - {symbol}")
                                        trade_amount = get_trade_amount(symbol, thread_id)
                                        if trade_amount and trade_amount >= Decimal(str(MIN_TRADE_AMOUNT)):
                                            if trade_amount >= capital[0]:
                                                if trade_amount >= capital[0] * Decimal("1.1"):
                                                    trade_amount = capital[0]
                                                else:
                                                    trade_amount = capital[0] * Decimal("0.9")
                                                trade_amount = Decimal(str(int(trade_amount)))
                                            process_trade = True
                                        else:
                                            logger.info(f"線程{thread_id}: {symbol} 投資金額不足最少交易金額，取消交易")
                                if process_trade:
                                    price, take_profit, stop_loss, profit_percentage, loss_percentage, profit_loss_ratio = tp_and_sl(df)
                                    logger.info(f"線程{thread_id}: 現價 - {price}, 止盈價 - {take_profit}, 止損價 - {stop_loss}")
                                    logger.info(f"線程{thread_id}: 報酬 - {(profit_percentage * 100):.2f}%, 損失 - {(loss_percentage * 100):.2f}%, 報酬風險比 - {profit_loss_ratio}")
                                    if profit_loss_ratio < Decimal("1.5"):
                                        logger.info(f"線程{thread_id}: {symbol} 報酬風險比少於 1.5，終止交易")
                                        raise NextSymbolCheck
                                    with capital_lock:
                                        if capital[0] >= trade_amount:
                                            new_thread_id = thread_id + 1
                                            logger.info(f"線程{thread_id}: 準備下一個線程，開啟新線程{new_thread_id}")
                                            threading.Thread(target=trade_searcher, args=(new_thread_id,), daemon=True).start()
                                            capital[0] -= trade_amount
                                            position = {
                                                'symbol': symbol,
                                                'amount': trade_amount,
                                                'entry_price': price,
                                                'take_profit': take_profit,
                                                'stop_loss': stop_loss,
                                                'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                                'current_price': price,
                                                'thread_id': thread_id,
                                                'profit_loss_ratio': profit_loss_ratio
                                            }
                                            positions.append(position)
                                            threading.Thread(target=monitor_position, args=(position,), daemon=True).start()
                                            total_positions = len(positions)
                                            positions_copy = deep_copy_positions(positions)
                                            capital_copy = capital[0]
                                            capital_copy = Decimal(str(capital_copy))
                                            capital_copy = f"{capital_copy:.2f}"
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
                                            raise ExitLoopException 
                                        else:
                                            raise NextSymbolCheck
                        except ccxt.BadSymbol:
                            pass
                        except NextSymbolCheck:
                            pass
                        except ExitLoopException:
                            logger.info(f"線程{thread_id}: 正常退出循環")
                            raise
                        except Exception as e:
                            logger.info(f"線程{thread_id}: 尋找 {symbol} 時發生錯誤: {e}\n{traceback.format_exc()}")
                    time.sleep(1)
                logger.info(f"線程{thread_id}: 第{round}次覆歷所有交易對，未找到交易機會")
                round += 1
                utc_tz = pytz.UTC
                CURRENT_DATE = datetime.now(utc_tz).date()
                closing_symbols = scan_markets(CURRENT_DATE)
                markets = exchange.fetch_markets()
                symbols = [market['symbol'] for market in markets if '/USDT' in market['symbol'] and ':USDT' not in market['symbol'] and market['active']]
                symbols = [symbol for symbol in symbols if not re.search(pattern, symbol)]
                symbols = [symbol for symbol in symbols if symbol not in closing_symbols]
                logger.info(f"線程{thread_id}: 已更新市場列表，繼續尋找交易機會")
        else:
            logger.info(f"線程{thread_id}: 不准許開啟新線程，退出線程")
    except ExitLoopException:
        logger.info(f"線程{thread_id}: 該線程已關閉")
    finally:
        with active_lock:
            search_threads_active -= 1
