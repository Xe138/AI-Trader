import os
from dotenv import load_dotenv
load_dotenv()
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import sys

# 将项目根目录加入 Python 路径，便于从子目录直接运行本文件
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from tools.general_tools import get_config_value
from api.database import get_db_connection

all_nasdaq_100_symbols = [
    "NVDA", "MSFT", "AAPL", "GOOG", "GOOGL", "AMZN", "META", "AVGO", "TSLA",
    "NFLX", "PLTR", "COST", "ASML", "AMD", "CSCO", "AZN", "TMUS", "MU", "LIN",
    "PEP", "SHOP", "APP", "INTU", "AMAT", "LRCX", "PDD", "QCOM", "ARM", "INTC",
    "BKNG", "AMGN", "TXN", "ISRG", "GILD", "KLAC", "PANW", "ADBE", "HON",
    "CRWD", "CEG", "ADI", "ADP", "DASH", "CMCSA", "VRTX", "MELI", "SBUX",
    "CDNS", "ORLY", "SNPS", "MSTR", "MDLZ", "ABNB", "MRVL", "CTAS", "TRI",
    "MAR", "MNST", "CSX", "ADSK", "PYPL", "FTNT", "AEP", "WDAY", "REGN", "ROP",
    "NXPI", "DDOG", "AXON", "ROST", "IDXX", "EA", "PCAR", "FAST", "EXC", "TTWO",
    "XEL", "ZS", "PAYX", "WBD", "BKR", "CPRT", "CCEP", "FANG", "TEAM", "CHTR",
    "KDP", "MCHP", "GEHC", "VRSK", "CTSH", "CSGP", "KHC", "ODFL", "DXCM", "TTD",
    "ON", "BIIB", "LULU", "CDW", "GFS"
]

def get_yesterday_date(today_date: str) -> str:
    """
    获取昨日日期，考虑休市日。
    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD，代表今天日期。

    Returns:
        yesterday_date: 昨日日期字符串，格式 YYYY-MM-DD。
    """
    # 计算昨日日期，考虑休市日
    today_dt = datetime.strptime(today_date, "%Y-%m-%d")
    yesterday_dt = today_dt - timedelta(days=1)
    
    # 如果昨日是周末，向前找到最近的交易日
    while yesterday_dt.weekday() >= 5:  # 5=Saturday, 6=Sunday
        yesterday_dt -= timedelta(days=1)
    
    yesterday_date = yesterday_dt.strftime("%Y-%m-%d")
    return yesterday_date

def get_open_prices(today_date: str, symbols: List[str], merged_path: Optional[str] = None, db_path: str = "data/jobs.db") -> Dict[str, Optional[float]]:
    """从 price_data 数据库表中读取指定日期与标的的开盘价。

    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD。
        symbols: 需要查询的股票代码列表。
        merged_path: 已废弃，保留用于向后兼容。
        db_path: 数据库路径，默认 data/jobs.db。

    Returns:
        {symbol_price: open_price 或 None} 的字典；若未找到对应日期或标的，则值为 None。
    """
    results: Dict[str, Optional[float]] = {}

    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()

        # Query all requested symbols for the date
        placeholders = ','.join('?' * len(symbols))
        query = f"""
            SELECT symbol, open
            FROM price_data
            WHERE date = ? AND symbol IN ({placeholders})
        """

        params = [today_date] + list(symbols)
        cursor.execute(query, params)

        # Build results dict
        for row in cursor.fetchall():
            symbol = row[0]
            open_price = row[1]
            results[f'{symbol}_price'] = float(open_price) if open_price is not None else None

        conn.close()

    except Exception as e:
        # Log error but return empty results to maintain compatibility
        print(f"Error querying price data: {e}")

    return results

def get_yesterday_open_and_close_price(today_date: str, symbols: List[str], merged_path: Optional[str] = None, db_path: str = "data/jobs.db") -> Tuple[Dict[str, Optional[float]], Dict[str, Optional[float]]]:
    """从 price_data 数据库表中读取指定日期与股票的昨日买入价和卖出价。

    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD，代表今天日期。
        symbols: 需要查询的股票代码列表。
        merged_path: 已废弃，保留用于向后兼容。
        db_path: 数据库路径，默认 data/jobs.db。

    Returns:
        (买入价字典, 卖出价字典) 的元组；若未找到对应日期或标的，则值为 None。
    """
    buy_results: Dict[str, Optional[float]] = {}
    sell_results: Dict[str, Optional[float]] = {}

    yesterday_date = get_yesterday_date(today_date)

    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()

        # Query all requested symbols for yesterday's date
        placeholders = ','.join('?' * len(symbols))
        query = f"""
            SELECT symbol, open, close
            FROM price_data
            WHERE date = ? AND symbol IN ({placeholders})
        """

        params = [yesterday_date] + list(symbols)
        cursor.execute(query, params)

        # Build results dicts
        for row in cursor.fetchall():
            symbol = row[0]
            open_price = row[1]  # Buy price (open)
            close_price = row[2]  # Sell price (close)

            buy_results[f'{symbol}_price'] = float(open_price) if open_price is not None else None
            sell_results[f'{symbol}_price'] = float(close_price) if close_price is not None else None

        conn.close()

    except Exception as e:
        # Log error but return empty results to maintain compatibility
        print(f"Error querying price data: {e}")

    return buy_results, sell_results

def get_yesterday_profit(today_date: str, yesterday_buy_prices: Dict[str, Optional[float]], yesterday_sell_prices: Dict[str, Optional[float]], yesterday_init_position: Dict[str, float]) -> Dict[str, float]:
    """
    获取今日开盘时持仓的收益，收益计算方式为：(昨日收盘价格 - 昨日开盘价格)*当前持仓。
    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD，代表今天日期。
        yesterday_buy_prices: 昨日开盘价格字典，格式为 {symbol_price: price}
        yesterday_sell_prices: 昨日收盘价格字典，格式为 {symbol_price: price}
        yesterday_init_position: 昨日初始持仓字典，格式为 {symbol: weight}

    Returns:
        {symbol: profit} 的字典；若未找到对应日期或标的，则值为 0.0。
    """
    profit_dict = {}
    
    # 遍历所有股票代码
    for symbol in all_nasdaq_100_symbols:
        symbol_price_key = f'{symbol}_price'
        
        # 获取昨日开盘价和收盘价
        buy_price = yesterday_buy_prices.get(symbol_price_key)
        sell_price = yesterday_sell_prices.get(symbol_price_key)
        
        # 获取昨日持仓权重
        position_weight = yesterday_init_position.get(symbol, 0.0)
        
        # 计算收益：(收盘价 - 开盘价) * 持仓权重
        if buy_price is not None and sell_price is not None and position_weight > 0:
            profit = (sell_price - buy_price) * position_weight
            profit_dict[symbol] = round(profit, 4)  # 保留4位小数
        else:
            profit_dict[symbol] = 0.0
    
    return profit_dict

def get_today_init_position(today_date: str, modelname: str) -> Dict[str, float]:
    """
    获取今日开盘时的初始持仓（即文件中上一个交易日代表的持仓）。从../data/agent_data/{modelname}/position/position.jsonl中读取。
    如果同一日期有多条记录，选择id最大的记录作为初始持仓。
    
    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD，代表今天日期。
        modelname: 模型名称，用于构建文件路径。

    Returns:
        {symbol: weight} 的字典；若未找到对应日期，则返回空字典。
    """
    base_dir = Path(__file__).resolve().parents[1]
    position_file = base_dir / "data" / "agent_data" / modelname / "position" / "position.jsonl"

    if not position_file.exists():
        print(f"Position file {position_file} does not exist")
        return {}
    
    yesterday_date = get_yesterday_date(today_date)
    max_id = -1
    latest_positions = {}
  
    with position_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                if doc.get("date") == yesterday_date:
                    current_id = doc.get("id", 0)
                    if current_id > max_id:
                        max_id = current_id
                        latest_positions = doc.get("positions", {})
            except Exception:
                continue
    
    return latest_positions

def get_latest_position(today_date: str, modelname: str) -> Tuple[Dict[str, float], int]:
    """
    获取最新持仓。从 ../data/agent_data/{modelname}/position/position.jsonl 中读取。
    优先选择当天 (today_date) 中 id 最大的记录；
    若当天无记录，则回退到上一个交易日，选择该日中 id 最大的记录。

    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD，代表今天日期。
        modelname: 模型名称，用于构建文件路径。

    Returns:
        (positions, max_id):
          - positions: {symbol: weight} 的字典；若未找到任何记录，则为空字典。
          - max_id: 选中记录的最大 id；若未找到任何记录，则为 -1.
    """
    base_dir = Path(__file__).resolve().parents[1]
    position_file = base_dir / "data" / "agent_data" / modelname / "position" / "position.jsonl"

    if not position_file.exists():
        return {}, -1
    
    # 先尝试读取当天记录
    max_id_today = -1
    latest_positions_today: Dict[str, float] = {}
    
    with position_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                if doc.get("date") == today_date:
                    current_id = doc.get("id", -1)
                    if current_id > max_id_today:
                        max_id_today = current_id
                        latest_positions_today = doc.get("positions", {})
            except Exception:
                continue
    
    if max_id_today >= 0:
        return latest_positions_today, max_id_today

    # 当天没有记录，则回退到上一个交易日
    prev_date = get_yesterday_date(today_date)
    max_id_prev = -1
    latest_positions_prev: Dict[str, float] = {}

    with position_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                if doc.get("date") == prev_date:
                    current_id = doc.get("id", -1)
                    if current_id > max_id_prev:
                        max_id_prev = current_id
                        latest_positions_prev = doc.get("positions", {})
            except Exception:
                continue

    return latest_positions_prev, max_id_prev

def add_no_trade_record(today_date: str, modelname: str):
    """
    添加不交易记录。从 ../data/agent_data/{modelname}/position/position.jsonl 中前一日最后一条持仓，并更新在今日的position.jsonl文件中。
    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD，代表今天日期。
        modelname: 模型名称，用于构建文件路径。

    Returns:
        None
    """
    save_item = {}
    current_position, current_action_id = get_latest_position(today_date, modelname)
    print(current_position, current_action_id)
    save_item["date"] = today_date
    save_item["id"] = current_action_id+1
    save_item["this_action"] = {"action":"no_trade","symbol":"","amount":0}
    
    save_item["positions"] = current_position
    base_dir = Path(__file__).resolve().parents[1]
    position_file = base_dir / "data" / "agent_data" / modelname / "position" / "position.jsonl"

    with position_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(save_item) + "\n")
    return


def get_today_init_position_from_db(
    today_date: str,
    modelname: str,
    job_id: str
) -> Dict[str, float]:
    """
    Query yesterday's position from SQLite database.

    Args:
        today_date: Current trading date (YYYY-MM-DD)
        modelname: Model signature
        job_id: Job UUID

    Returns:
        Position dict: {"AAPL": 50, "MSFT": 30, "CASH": 5000.0}
        If no position exists: {"CASH": 10000.0} (initial cash)
    """
    import logging
    from tools.deployment_config import get_db_path
    from api.database import get_db_connection

    logger = logging.getLogger(__name__)

    db_path = get_db_path()
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    try:
        # Get most recent position before today
        cursor.execute("""
            SELECT p.id, p.cash
            FROM positions p
            WHERE p.job_id = ? AND p.model = ? AND p.date < ?
            ORDER BY p.date DESC, p.action_id DESC
            LIMIT 1
        """, (job_id, modelname, today_date))

        row = cursor.fetchone()

        if not row:
            # First day - return initial cash
            logger.info(f"No previous position found for {modelname}, returning initial cash")
            return {"CASH": 10000.0}

        position_id, cash = row
        position_dict = {"CASH": cash}

        # Get holdings for this position
        cursor.execute("""
            SELECT symbol, quantity
            FROM holdings
            WHERE position_id = ?
        """, (position_id,))

        for symbol, quantity in cursor.fetchall():
            position_dict[symbol] = quantity

        logger.debug(f"Loaded position for {modelname}: {position_dict}")
        return position_dict

    except Exception as e:
        logger.error(f"Database error in get_today_init_position_from_db: {e}")
        raise
    finally:
        conn.close()


def add_no_trade_record_to_db(
    today_date: str,
    modelname: str,
    job_id: str,
    session_id: int
) -> None:
    """
    Create no-trade position record in SQLite database.

    Args:
        today_date: Current trading date (YYYY-MM-DD)
        modelname: Model signature
        job_id: Job UUID
        session_id: Trading session ID
    """
    import logging
    from tools.deployment_config import get_db_path
    from api.database import get_db_connection
    from agent_tools.tool_trade import get_current_position_from_db
    from datetime import datetime

    logger = logging.getLogger(__name__)

    db_path = get_db_path()
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    try:
        # Get current position
        current_position, next_action_id = get_current_position_from_db(
            job_id, modelname, today_date
        )

        # Calculate portfolio value
        cash = current_position.get("CASH", 0.0)
        portfolio_value = cash

        # Add stock values
        for symbol, qty in current_position.items():
            if symbol != "CASH":
                try:
                    price = get_open_prices(today_date, [symbol])[f'{symbol}_price']
                    portfolio_value += qty * price
                except KeyError:
                    logger.warning(f"Price not found for {symbol} on {today_date}")
                    pass

        # Get previous value for P&L
        cursor.execute("""
            SELECT portfolio_value
            FROM positions
            WHERE job_id = ? AND model = ? AND date < ?
            ORDER BY date DESC, action_id DESC
            LIMIT 1
        """, (job_id, modelname, today_date))

        row = cursor.fetchone()
        previous_value = row[0] if row else 10000.0

        daily_profit = portfolio_value - previous_value
        daily_return_pct = (daily_profit / previous_value * 100) if previous_value > 0 else 0

        # Insert position record
        created_at = datetime.utcnow().isoformat() + "Z"

        cursor.execute("""
            INSERT INTO positions (
                job_id, date, model, action_id, action_type,
                cash, portfolio_value, daily_profit, daily_return_pct,
                session_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, today_date, modelname, next_action_id, "no_trade",
            cash, portfolio_value, daily_profit, daily_return_pct,
            session_id, created_at
        ))

        position_id = cursor.lastrowid

        # Insert holdings (unchanged from previous position)
        for symbol, qty in current_position.items():
            if symbol != "CASH":
                cursor.execute("""
                    INSERT INTO holdings (position_id, symbol, quantity)
                    VALUES (?, ?, ?)
                """, (position_id, symbol, qty))

        conn.commit()
        logger.info(f"Created no-trade record for {modelname} on {today_date}")

    except Exception as e:
        conn.rollback()
        logger.error(f"Database error in add_no_trade_record_to_db: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    today_date = get_config_value("TODAY_DATE")
    signature = get_config_value("SIGNATURE")
    if signature is None:
        raise ValueError("SIGNATURE environment variable is not set")
    print(today_date, signature)
    yesterday_date = get_yesterday_date(today_date)
    # print(yesterday_date)
    today_buy_price = get_open_prices(today_date, all_nasdaq_100_symbols)
    # print(today_buy_price)
    yesterday_buy_prices, yesterday_sell_prices = get_yesterday_open_and_close_price(today_date, all_nasdaq_100_symbols)
    # print(yesterday_buy_prices)
    # print(yesterday_sell_prices)
    today_init_position = get_today_init_position(today_date, signature)
    # print(today_init_position)
    latest_position, latest_action_id = get_latest_position(today_date, signature)
    print(latest_position, latest_action_id)
    yesterday_profit = get_yesterday_profit(today_date, yesterday_buy_prices, yesterday_sell_prices, today_init_position)
    # print(yesterday_profit)
    add_no_trade_record(today_date, signature)
