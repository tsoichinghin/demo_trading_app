# demo_trading_app
這是一個幣安現貨模擬交易程式。

1. /app/config.py
修改TIMEFRAME變量為想要的K線時間圖
修改INITIAL_CAPITAL為想要的起始本金
修改MIN_TRADE_AMOUNT為想要的最低每單投資金額

2. /app/exchange_utils.py
在calculate_indicators()中加入想要使用的指標，計算方法自備。但已附送上四個指標。
在check_conditions()利用已計算指標設定開單條件
在tp_and_sl()設定自己想要的止盈價和止損價，已有預設邏輯，可自行修改。
get_trade_amount()和classify_liquidity()不建議修改，兩個function用於計算每單的投資金額，該投資金額建基於該交易對的每秒成交額與訂單簿權重，原旨為避免關單時市場需求不高，而引致無法即時成交的情況。

3. /app/martet_scanner.py
請不要修改，用於檢查幣安即將關閉的交易對市場，如出現即將關閉的交易對，將刪除在尋找交易對機會的列表中。
此功能為避免出現開單後，因交易對關閉而無法賣出成交。

4. /app/trading_logic.py
關於trade_searcher()：
1) 當中有如於指定時間內，該交易對曾開單，將skip過該交易對。預設為30分鐘時圖，所以為30分鐘內開單，則skip過交易對。
代碼於166行至175行
// current_time = datetime.now()
thirty_minutes_ago = current_time - timedelta(minutes=30)
has_recent_trade = any(
    trade['symbol'] == symbol and 
    datetime.strptime(trade['open_time'], '%Y-%m-%d %H:%M:%S') >= thirty_minutes_ago
    for trade in trade_history
)
if has_recent_trade:
    logger.info(f"線程{thread_id}: {symbol} 在過去 30 分鐘內曾開過單，跳過")
    continue //
如不需請刪去，或修改為想要之時間間隔。

2) 計算指標，修改獲取幣安交易所K線周期資料之變量。請修改至你需要的周期數，預設為340周期。（不建議過高，或許會觸及幣安Rest API Limit）
代碼於177行至178行
//df = get_historical_data(symbol, 340)
if len(df) < 340://
340行為計算ema100的最好周期數

3) 報酬風險比 - 有預設報酬風險比不高於1.5則取消開單的功能。
代碼為201行至203行
//if profit_loss_ratio < Decimal("1.5"):
logger.info(f"線程{thread_id}: {symbol} 報酬風險比少於 1.5，終止交易")
raise NextSymbolCheck//
如不需請刪去，或修改為想要之比率

關於monitor_position()與close_position()：
如有別的關單邏輯，請修改以下行代碼。
代碼於56行至61行

//if current_price >= position['take_profit']:
close_position(position, '止盈', position['take_profit'], position['thread_id'])
break
elif current_price <= position['stop_loss']:
close_position(position, '止損', current_price, position['thread_id'])
break//

預設關單邏輯為止盈與止損，如有別的關單邏輯，請自行修改。
close_position的接入變量為(position, 關單原因, 關單價格, position['thread_id'])
如有別的關單原因，請一同修改close_position()的69行至86行代碼

//if reason == '止損':
crypto_amount = position['amount'] / position['entry_price']
crypto_amount_after_fee = crypto_amount * Decimal("0.999")
after_exit_usdt_amount = crypto_amount_after_fee * excute_price
after_exit_usdt_amount_after_fee = after_exit_usdt_amount * Decimal("0.999")
pnl = after_exit_usdt_amount_after_fee - position['amount']
capital = capital + position['amount'] + pnl
change_percentage = abs(pnl) / position['amount'] * 100
if pnl < 0:
change_percentage = -change_percentage
elif reason == '止盈':
crypto_amount = position['amount'] / position['entry_price']
crypto_amount_after_fee = crypto_amount * Decimal("0.999")
after_exit_usdt_amount = crypto_amount_after_fee * excute_price
after_exit_usdt_amount_after_fee = after_exit_usdt_amount * Decimal("0.999")
pnl = after_exit_usdt_amount_after_fee - position['amount']
capital = capital + position['amount'] + pnl
change_percentage = abs(pnl) / position['amount'] * 100//

建議只修改reason，其餘為已正確計算幣安手續費之步驟。

5. /app/web_interface.py
請不要修改。

6. /templates/logs.html
如果想以VPS 24/7運行程式，請把第55行的：「var socket = io('http://localhost:8888');」中的localhost改為VPS的外部IP。

7. requirement.txt
運行前安裝所需依賴項，運行以下命令：「pip install -r requirement.txt」

8. 運行程式
python3 main.py

9. 實時監控
請於瀏覽器連結：「http://localhost:8888」，使用此程式。
程式的logs會一併於查看日誌位置出現，最多為100行，新的蓋過舊的log。
已關單交易則於查看歷史中出現。
已關單交易也會一併儲存於results/results.csv，但請注意每開啟一次程式，results.csv將會清空，請自行備份。
切換尋找新交易對按鍵，為控制trading_logic.py中的trade_searcher()。如狀態為disabled，將不開啟新的trade_searcher()之線程。舊的已開單線程仍然運作，直至關單為至。如trade_searcher()的線程為零，將會開啟新線程。
