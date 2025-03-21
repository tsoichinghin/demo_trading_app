import pandas as pd
from .config import exchange, TIMEFRAME, logger
from decimal import Decimal, ROUND_HALF_UP

def get_historical_data(symbol, limit):
    ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calculate_indicators(df):
    # EMA
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema100'] = df['close'].ewm(span=100, adjust=False).mean()
    # MACD
    exp12 = df['close'].ewm(span=12, adjust=False).mean()
    exp26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp12 - exp26
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['histogram'] = df['macd'] - df['signal']
    # KD
    low_9 = df['low'].rolling(9).min()
    high_9 = df['high'].rolling(9).max()
    rsv = (df['close'] - low_9) / (high_9 - low_9) * 100
    df['k'] = rsv.ewm(span=3, adjust=False).mean()
    df['d'] = df['k'].ewm(span=3, adjust=False).mean()
    # ATR
    df['previous_close'] = df['close'].shift(1)
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = abs(df['high'] - df['previous_close'])
    df['tr3'] = abs(df['low'] - df['previous_close'])
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    return df

def check_ema_trend(df, periods):
    # 可用於檢查過往周期有多少周期符合EMA條件
    fix_cond = 0
    for i in range(-1, -(periods + 1), -1):
        if (df['ema20'].iloc[i] > df['ema50'].iloc[i] > df['ema100'].iloc[i]): # ema20 > ema50 > ema100
            fix_cond += 1
    return (fix_cond / periods) >= 0.8 # 過往測試周期大於8成符合條件

def check_conditions(df):
    row = df.iloc[-1] # 現周期
    prev_row = df.iloc[-2] # 前周期
    prev_prev_row = df.iloc[-3] # 前前周期
    example_cond = ((row['close'] > prev_row['high']) and (row['low'] > prev_row['low']) and
                  (row['close'] > row['open']) and (prev_row['close'] > prev_row['open']) and
                  (prev_prev_row['close'] < prev_prev_row['open']) and (prev_row['close'] > prev_prev_row['close']))
    example_cond_2 = ((row['signal'] > row['macd']) and (prev_row['macd'] > prev_row['signal']))
    return all([example_cond, example_cond_2])

def fetch_all_trades(symbol, thread_id, duration_minutes, limit):
    all_trades = []
    end_time = exchange.milliseconds()
    start_time = end_time - duration_minutes * 60 * 1000
    current_since = start_time
    
    while current_since < end_time:
        try:
            trades = exchange.fetch_trades(symbol, since=current_since, limit=limit, params={'endTime': end_time})
            if not trades:
                break
            all_trades.extend(trades)
            if len(trades) < limit:
                break
            last_trade_time = trades[-1]['timestamp']
            if last_trade_time >= end_time:
                break
            current_since = last_trade_time + 1
        except Exception as e:
            logger.info(f"線程{thread_id}: {symbol} 獲取交易數據時出錯: {e}")
            break
    return all_trades

def classify_liquidity(symbol, thread_id):
    try:
        ticker = exchange.fetch_ticker(symbol)
        quote_volume_24h = ticker['quoteVolume']
        avps = quote_volume_24h / 86400
        orderbook = exchange.fetch_order_book(symbol, limit=2000)
        current_price = ticker['last']
        bids = orderbook['bids']
        bid_depth_01 = sum(price * amount for price, amount in bids if price >= current_price * 0.999)
        bid_depth_05 = sum(price * amount for price, amount in bids if price >= current_price * 0.995)
        bid_depth_1 = sum(price * amount for price, amount in bids if price >= current_price * 0.99)
        bid_depth_01_trade = sum(1 for price, _ in bids if price >= current_price * 0.999)
        bid_depth_05_trade = sum(1 for price, _ in bids if price >= current_price * 0.995)
        bid_depth_1_trade = sum(1 for price, _ in bids if price >= current_price * 0.99)
        average_depth_01 = bid_depth_01 / bid_depth_01_trade if bid_depth_01_trade > 0 else 0
        average_depth_05 = bid_depth_05 / bid_depth_05_trade if bid_depth_05_trade > 0 else 0
        average_depth_1 = bid_depth_1 / bid_depth_1_trade if bid_depth_1_trade > 0 else 0
        total_trades = bid_depth_1_trade
        w_01 = bid_depth_01_trade / total_trades if total_trades > 0 else 0
        w_05 = (bid_depth_05_trade - bid_depth_01_trade) / total_trades if total_trades > 0 else 0
        w_1 = (bid_depth_1_trade - bid_depth_05_trade) / total_trades if total_trades > 0 else 0
        average_depth = w_01 * average_depth_01 + w_05 * average_depth_05 + w_1 * average_depth_1
        min_trades = 1
        effective_trade_count = max(bid_depth_01_trade, min_trades)
        bid_depth = average_depth * effective_trade_count
        total_bid_depth = sum(price * amount for price, amount in bids)
        trades = fetch_all_trades(symbol, thread_id, 5, 2000)
        market_trade_volume = sum(trade['amount'] * trade['price'] for trade in trades)
        market_trade_volume_per_second = market_trade_volume / (5 * 60)
        logger.info(f"線程{thread_id}: {symbol} - 即時價格: {current_price}, 前三筆買單: {bids[:3]}")
        logger.info(f"線程{thread_id}: {symbol} - 訂單簿長度: {len(bids)}")
        logger.info(f"線程{thread_id}: {symbol} - 訂單簿1%內總訂單數量: {total_trades}, 0.1%內的訂單數量: {bid_depth_01_trade}")
        logger.info(f"線程{thread_id}: {symbol} - 總深度: {total_bid_depth:.2f}, 權重深度: {bid_depth:.2f}, 5分鐘市價總成交額: {market_trade_volume:.2f}, 每秒市價成交額: {market_trade_volume_per_second:.2f}")
        k_depth = bid_depth / avps if avps > 0 else 0
        k_market = market_trade_volume_per_second / avps if avps > 0 else 0
        k_time = int(k_depth / k_market) if k_market != 0 else 0
        if k_depth >= k_market * 3200:
            k = (k_depth * 0.00015625 + k_market * 0.99984375)
            depth = k * avps if avps > 0 else 0
            depth_type = "混合式"
        elif k_depth >= k_market * 1600:
            k = (k_depth * 0.0003125 + k_market * 0.9996875)
            depth = k * avps if avps > 0 else 0
            depth_type = "混合式"
        elif k_depth >= k_market * 800:
            k = (k_depth * 0.000625 + k_market * 0.999375)
            depth = k * avps if avps > 0 else 0
            depth_type = "混合式"
        elif k_depth >= k_market * 400:
            k = (k_depth * 0.00125 + k_market * 0.99875)
            depth = k * avps if avps > 0 else 0
            depth_type = "混合式"
        elif k_depth >= k_market * 300:
            k = (k_depth * 0.001875 + k_market * 0.998125)
            depth = k * avps if avps > 0 else 0
            depth_type = "混合式"
        elif k_depth >= k_market * 200:
            k = (k_depth * 0.0025 + k_market * 0.9975)
            depth = k * avps if avps > 0 else 0
            depth_type = "混合式"
        elif k_depth >= k_market * 150:
            k = (k_depth * 0.00375 + k_market * 0.99625)
            depth = k * avps if avps > 0 else 0
            depth_type = "混合式"
        elif k_depth >= k_market * 100:
            k = (k_depth * 0.005 + k_market * 0.995)
            depth = k * avps if avps > 0 else 0
            depth_type = "混合式"
        elif k_depth >= k_market * 75:
            k = (k_depth * 0.0075 + k_market * 0.9925)
            depth = k * avps if avps > 0 else 0
            depth_type = "混合式"
        elif k_depth >= k_market * 50:
            k = (k_depth * 0.01 + k_market * 0.99)
            depth = k * avps if avps > 0 else 0
            depth_type = "混合式"
        elif k_depth >= k_market * 35:
            k = (k_depth * 0.025 + k_market * 0.975)
            depth = k * avps if avps > 0 else 0
            depth_type = "混合式"
        elif k_depth >= k_market * 20:
            k = (k_depth * 0.04 + k_market * 0.96)
            depth = k * avps if avps > 0 else 0
            depth_type = "混合式"
        elif k_depth >= k_market * 10:
            k = (k_depth * 0.08 + k_market * 0.92)
            depth = k * avps if avps > 0 else 0
            depth_type = "混合式"
        elif k_depth >= k_market * 5:
            k = (k_depth * 0.15 + k_market * 0.85)
            depth = k * avps if avps > 0 else 0
            depth_type = "混合式"
        elif k_depth >= k_market * 3:
            k = (k_depth * 0.3 + k_market * 0.7)
            depth = k * avps if avps > 0 else 0
            depth_type = "混合式"
        elif k_depth >= k_market * 1.5:
            k = (k_depth * 0.5 + k_market * 0.5)
            depth = k * avps if avps > 0 else 0
            depth_type = "混合式"
        else:
            k = max(k_depth, k_market)
            if k_market > k_depth:
                depth = market_trade_volume_per_second
                depth_type = "市價單"
            else:
                depth = bid_depth
                depth_type = "訂單簿"
        if k >= 3:
            factor = k
            return 'Extremely', factor, k, depth, depth_type, k_time
        elif k >= 1.5:
            factor = k
            return 'High', factor, k, depth, depth_type, k_time
        else:
            factor = k
            return 'Normal', factor, k, depth, depth_type, k_time
    except Exception as e:
        logger.info(f"線程{thread_id} 分類 {symbol} 流動性時出錯: {e}")
        return 'low', 1, 'error', 'error', 'error', 0

def get_trade_amount(symbol, thread_id):
    liquidity_type, safety_factor, k, depth, depth_type, k_time = classify_liquidity(symbol, thread_id)
    ticker = exchange.fetch_ticker(symbol)
    quote_volume_24h = ticker['quoteVolume']
    avps = quote_volume_24h / 86400 * 0.9
    safe_amount = Decimal(str(int(avps * safety_factor)))
    logger.info(f"線程{thread_id}: {symbol} - 訂單簿深度是過去五分鐘的每秒成交量的{k_time}倍")
    logger.info(f"線程{thread_id}: {symbol} - 流動性: {liquidity_type}, {depth_type}深度: {depth:.2f}, AVPS: {avps:.2f}, K: {k:.2f}, 安全倍數: {safety_factor}, 交易金額: {safe_amount}")
    return safe_amount

def tp_and_sl(df):
    price = Decimal(str(df['close'].iloc[-1]))
    prev_row = df.iloc[-2] # 前周期
    highest_high = df['high'].iloc[max(0, prev_row.name - 9):prev_row.name + 1].max() # 以前周期為起點，過往9周期+前周期的最高高點
    lowest_low = df['low'].iloc[max(0, prev_row.name - 9):prev_row.name + 1].min() # 以前周期為起點，過往9周期+前周期的最低低點
    take_profit = Decimal(str(((highest_high - lowest_low) * 0.8) + lowest_low)) # TP為低點與高點間的8成價位
    take_profit = take_profit.quantize(Decimal('1.' + '0' * (-price.as_tuple().exponent)), rounding=ROUND_HALF_UP)
    stop_loss = Decimal(str(lowest_low)) # SL為最低低點
    profit_percentage = (Decimal((take_profit - price) / price) - Decimal("0.002"))
    loss_percentage = (Decimal((price - stop_loss) / price) + Decimal("0.002"))
    profit_loss_ratio = Decimal(f"{(profit_percentage / loss_percentage):.2f}")
    return price, take_profit, stop_loss, profit_percentage, loss_percentage, profit_loss_ratio
