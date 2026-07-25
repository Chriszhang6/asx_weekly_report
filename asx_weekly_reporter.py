#!/usr/bin/env python3
"""
ASX Weekly Investment Report Generator
自动生成澳洲股票投资周报并发送邮件
集成WebSearch获取实时数据
"""

import os
import smtplib
import re
import statistics
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from datetime import datetime, timedelta
from pathlib import Path
import time
import requests

# ============== 配置区域 ==============
# 从环境变量读取配置
GMAIL_ADDRESS = os.getenv('GMAIL_ADDRESS', '')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD', '')
RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL', GMAIL_ADDRESS)  # 默认发送给自己

# 清理特殊字符（非断空格等）
def clean_string(s: str) -> str:
    """清理字符串中的特殊字符"""
    if s:
        # 替换非断空格（\xa0）为普通空格，然后删除所有空格
        return s.replace('\xa0', ' ').replace(' ', '')
    return s

GMAIL_APP_PASSWORD = clean_string(GMAIL_APP_PASSWORD)

# 输出目录 - GitHub Actions使用docs目录，本地使用Downloads目录，可通过环境变量覆盖
output_dir_env = os.getenv('OUTPUT_DIR')
if output_dir_env:
    OUTPUT_DIR = Path(output_dir_env)
elif os.getenv('GITHUB_ACTIONS') == 'true':
    OUTPUT_DIR = Path('./docs')
else:
    OUTPUT_DIR = Path.home() / 'Downloads' / 'asx_weekly_report'
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

KEY_STOCKS = [
    ("BHP.AX", "BHP Group"),
    ("CBA.AX", "Commonwealth Bank"),
    ("CSL.AX", "CSL Ltd"),
    ("NAB.AX", "National Australia Bank"),
    ("WBC.AX", "Westpac"),
    ("ANZ.AX", "ANZ Group"),
    ("WES.AX", "Wesfarmers"),
    ("WOW.AX", "Woolworths"),
    ("RIO.AX", "Rio Tinto"),
    ("FMG.AX", "Fortescue Metals"),
    ("MQG.AX", "Macquarie Group"),
    ("TLS.AX", "Telstra"),
    ("WDS.AX", "Woodside Energy"),
    ("ALL.AX", "Aristocrat Leisure"),
    ("QAN.AX", "Qantas Airways"),
]

STOCK_KEYWORDS = {
    "BHP": ["bhp", "iron ore", "china", "miner", "mining"],
    "RIO": ["rio", "iron ore", "china", "miner", "mining"],
    "FMG": ["fortescue", "iron ore", "china", "miner", "mining"],
    "CBA": ["cba", "commonwealth bank", "bank", "banks", "rate", "mortgage"],
    "NAB": ["nab", "national australia bank", "bank", "banks", "rate", "mortgage"],
    "WBC": ["wbc", "westpac", "bank", "banks", "rate", "mortgage"],
    "ANZ": ["anz", "bank", "banks", "rate", "mortgage"],
    "MQG": ["mqg", "macquarie", "bank", "markets", "deal"],
    "CSL": ["csl", "health", "healthcare", "defensive"],
    "WES": ["wes", "wesfarmers", "consumer", "retail", "spending"],
    "WOW": ["wow", "woolworths", "consumer", "retail", "spending"],
    "TLS": ["tls", "telstra", "telecom", "yield"],
    "WDS": ["wds", "woodside", "oil", "energy", "lng"],
    "ALL": ["all", "aristocrat", "gaming", "consumer"],
    "QAN": ["qan", "qantas", "travel", "consumer"],
}

EVENT_RULES = [
    {"name": "RBA利率决议", "weekday": 1, "occurrence": 1, "impact": "市场将关注政策措辞对银行股和澳元的影响"},
    {"name": "NAB商业景气调查", "weekday": 1, "occurrence": 2, "impact": "反映企业投资与需求强弱，常影响周期股预期"},
    {"name": "Westpac消费者信心指数", "weekday": 2, "occurrence": 2, "impact": "可作为零售和可选消费板块的先行温度计"},
    {"name": "澳大利亚就业数据", "weekday": 3, "occurrence": 3, "impact": "就业与工资压力会直接影响降息预期"},
    {"name": "RBA会议纪要", "weekday": 1, "occurrence": 3, "impact": "若措辞偏鹰派，利率敏感板块波动可能放大"},
    {"name": "澳大利亚月度CPI指标", "weekday": 2, "occurrence": -1, "impact": "通胀路径若偏离预期，市场会重新定价利率路径"},
]


def _format_pct(value: float | None) -> str:
    """格式化百分比数值"""
    if value is None:
        return "N/A"
    return f"{value:+.2f}%"


def _format_price(value: float | None) -> str:
    """格式化价格数值"""
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def _safe_pct_change(new_value: float | None, old_value: float | None) -> float | None:
    """计算百分比变化"""
    if new_value is None or old_value in (None, 0):
        return None
    return ((new_value - old_value) / old_value) * 100


def _nth_weekday_of_month(year: int, month: int, weekday: int, occurrence: int) -> datetime | None:
    """获取某月第N个工作日；occurrence=-1 表示最后一个"""
    first_day = datetime(year, month, 1)
    dates = []
    current = first_day
    while current.month == month:
        if current.weekday() == weekday:
            dates.append(current)
        current += timedelta(days=1)

    if not dates:
        return None
    if occurrence == -1:
        return dates[-1]
    index = occurrence - 1
    if 0 <= index < len(dates):
        return dates[index]
    return None


def _extract_lines_by_keywords(content: str, keywords: list[str], limit: int) -> list[str]:
    """从文本中提取包含关键词的行"""
    extracted = []
    for line in content.split('\n'):
        text = line.strip()
        if not (20 < len(text) < 200):
            continue
        if any(skip in text for skip in ['MENU', 'Skip to', 'Login', 'Subscribe', '***', '---', '|||']):
            continue
        text_lower = text.lower()
        if any(keyword.lower() in text_lower for keyword in keywords):
            if text not in extracted:
                extracted.append(text)
        if len(extracted) >= limit:
            break
    return extracted


# ============== 实时数据获取函数 ==============

def fetch_url(url: str, timeout: int = 30) -> str:
    """
    获取网页内容

    Args:
        url: 网页URL
        timeout: 超时时间

    Returns:
        网页文本内容
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()

        # 简单提取文本内容（去除HTML标签）
        import html2text
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        text = h.handle(response.text)

        return text[:10000]  # 限制长度，避免上下文过长

    except ImportError:
        # 如果没有html2text，使用简单的正则提取
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=timeout)
        response.raise_for_status()
        # 简单去除HTML标签
        text = re.sub(r'<[^>]+>', '\n', response.text)
        text = re.sub(r'\n+', '\n', text)
        return text[:10000]

    except Exception as e:
        return f"获取网页失败: {str(e)}"


def get_real_time_data() -> str:
    """
    获取实时ASX市场数据
    通过抓取Yahoo Finance HTML页面获取最新信息

    Returns:
        格式化的实时数据文本
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🌐 正在获取实时市场数据...")

    context_parts = []
    current_date = datetime.now().strftime("%Y年%m月%d日")

    try:
        # ========== 1. 获取S&P/ASX 200指数数据 ==========
        print("    📊 获取S&P/ASX 200指数...")
        asx200_data = _fetch_yahoo_finance_data("%5EAXJO")  # URL encoded ^AXJO

        # 解析涨跌幅
        change_pct = None
        if "涨跌幅" in asx200_data:
            match = re.search(r'涨跌幅.*?([-\d.]+)%', asx200_data)
            if match:
                change_pct = float(match.group(1))

        if asx200_data:
            market_data = f"""
## 📊 S&P/ASX 200 指数表现 ({current_date})

{asx200_data}

"""
            context_parts.append(market_data)
            print(f"    ✅ ASX 200数据已获取")

        # ========== 2. 大幅涨跌时获取原因 ==========
        if change_pct is not None and abs(change_pct) >= 1.5:
            print(f"    📰 涨跌幅达到 {change_pct:+.2f}%，获取市场原因...")
            reason_data = _fetch_market_reasons()
            if reason_data:
                context_parts.append(f"""
## 📈 市场变动原因

{reason_data}
""")

        # ========== 3. 获取主要个股数据 ==========
        print("    📊 获取主要个股数据...")
        stock_data = _fetch_key_stocks_data()
        if stock_data:
            context_parts.append(stock_data)

        # ========== 4. 获取市场新闻 ==========
        print("    📰 获取市场新闻...")
        news_data = _fetch_market_news()
        if news_data:
            context_parts.append(news_data)

        result = "\n".join(context_parts)
        print(f"    ✅ 已获取完整的实时市场数据")

        return result

    except Exception as e:
        print(f"    ❌ 获取数据失败: {e}")
        print("    🔄 尝试使用备用网页抓取...")
        return _get_real_time_data_from_web()


def _fetch_yahoo_finance_quote_data(ticker_symbol: str, company_name: str = "") -> dict:
    """
    从Yahoo Finance HTML页面抓取股票/指数结构化数据
    """
    quote = {
        "ticker": ticker_symbol,
        "code": ticker_symbol.replace("%5E", "").replace("^", "").replace(".AX", ""),
        "name": company_name or ticker_symbol.replace(".AX", ""),
        "price": None,
        "change": None,
        "change_pct": None,
        "prev_close": None,
        "day_high": None,
        "day_low": None,
        "volume": None,
        "error": "",
    }

    try:
        url = f"https://au.finance.yahoo.com/quote/{ticker_symbol}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-AU,en;q=0.9',
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        content = response.text

        field_patterns = {
            "price": r'"regularMarketPrice":\s*\{[^}]*"raw":\s*([-\d.]+)',
            "prev_close": r'"regularMarketPreviousClose":\s*\{[^}]*"raw":\s*([-\d.]+)',
            "change": r'"regularMarketChange":\s*\{[^}]*"raw":\s*([-\d.]+)',
            "change_pct": r'"regularMarketChangePercent":\s*\{[^}]*"raw":\s*([-\d.]+)',
            "day_high": r'"regularMarketDayHigh":\s*\{[^}]*"raw":\s*([-\d.]+)',
            "day_low": r'"regularMarketDayLow":\s*\{[^}]*"raw":\s*([-\d.]+)',
            "volume": r'"regularMarketVolume":\s*\{[^}]*"raw":\s*(\d+)',
        }

        for field_name, pattern in field_patterns.items():
            match = re.search(pattern, content)
            if not match:
                continue
            if field_name == "volume":
                quote[field_name] = int(match.group(1))
            else:
                quote[field_name] = float(match.group(1))

        if quote["price"] is None:
            quote["error"] = "无法解析价格数据"
    except Exception as e:
        quote["error"] = str(e)

    if quote["price"] is None:
        history = _fetch_yahoo_chart_data(ticker_symbol, period_days=10)
        if history:
            quote["price"] = history[-1]["close"]
            quote["prev_close"] = history[-2]["close"] if len(history) >= 2 else None
            quote["change"] = (
                quote["price"] - quote["prev_close"]
                if quote["price"] is not None and quote["prev_close"] is not None
                else None
            )
            quote["change_pct"] = _safe_pct_change(quote["price"], quote["prev_close"])
            quote["day_high"] = quote["price"]
            quote["day_low"] = quote["price"]
            quote["volume"] = history[-1]["volume"]
            quote["error"] = ""

    return quote


def _fetch_yahoo_finance_data(ticker_symbol: str) -> str:
    """
    从Yahoo Finance HTML页面抓取股票/指数数据并格式化输出
    """
    quote = _fetch_yahoo_finance_quote_data(ticker_symbol)
    if quote["price"] is None:
        return f"⚠️ 获取失败: {quote['error'] or '无法解析价格数据'}"

    result = f"- **当前价格**: {_format_price(quote['price'])}\n"
    if quote["change"] is not None:
        result += f"- **涨跌额**: {quote['change']:+.2f}\n"
    if quote["change_pct"] is not None:
        result += f"- **涨跌幅**: {_format_pct(quote['change_pct'])}\n"
    if quote["prev_close"] is not None:
        result += f"- **前收盘**: {_format_price(quote['prev_close'])}\n"
    if quote["day_high"] is not None:
        result += f"- **今日最高**: {_format_price(quote['day_high'])}\n"
    if quote["day_low"] is not None:
        result += f"- **今日最低**: {_format_price(quote['day_low'])}\n"
    if quote["volume"]:
        result += f"- **成交量**: {quote['volume']:,}\n"
    return result


def _fetch_yahoo_chart_data(ticker_symbol: str, period_days: int = 40) -> list[dict]:
    """获取Yahoo Finance历史行情数据"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period_days)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_symbol}"
        params = {
            "period1": int(start_date.timestamp()),
            "period2": int(end_date.timestamp()),
            "interval": "1d",
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        payload = response.json()
        result = payload.get("chart", {}).get("result", [])
        if not result:
            return []

        timestamps = result[0].get("timestamp", [])
        quote_data = result[0].get("indicators", {}).get("quote", [{}])[0]
        closes = quote_data.get("close", [])
        volumes = quote_data.get("volume", [])

        history = []
        for timestamp, close, volume in zip(timestamps, closes, volumes):
            if close is None:
                continue
            history.append({
                "date": datetime.fromtimestamp(timestamp),
                "close": float(close),
                "volume": int(volume) if volume is not None else None,
            })
        return history
    except Exception:
        return []


def _fetch_key_stocks_data() -> str:
    """
    获取ASX主要权重股的实时价格数据
    """
    stock_lines = []
    for quote in _fetch_key_stock_quotes():
        if quote["price"] is not None:
            line = f"- **{quote['code']} ({quote['name']})**: ${_format_price(quote['price'])}"
            if quote["change_pct"] is not None:
                line += f", 涨跌幅 {_format_pct(quote['change_pct'])}"
            if quote["change"] is not None:
                line += f" ({quote['change']:+.2f})"
            stock_lines.append(line)
            print(f"        ✅ {quote['code']}: ${_format_price(quote['price'])} ({_format_pct(quote['change_pct'])})")
        else:
            print(f"        ⚠️ {quote['ticker']}: 数据获取失败")

    if stock_lines:
        return "## 📊 主要个股表现\n\n" + "\n".join(stock_lines) + "\n"
    return ""


def _fetch_key_stock_quotes() -> list[dict]:
    """获取核心股票列表的结构化行情"""
    quotes = []
    for ticker, name in KEY_STOCKS:
        quote = _fetch_yahoo_finance_quote_data(ticker, name)
        quotes.append(quote)
        time.sleep(0.3)
    return quotes


def _fetch_market_news() -> str:
    """
    获取市场新闻（辅助函数）
    """
    news_parts = []
    for source_name, news_items in _fetch_market_news_items().items():
        if news_items:
            news_parts.append(f"### {source_name}\n\n" + "\n".join(f"- {item}" for item in news_items))

    if news_parts:
        return "## 📰 市场新闻\n\n" + "\n\n".join(news_parts)
    return ""


def _fetch_market_news_items() -> dict[str, list[str]]:
    """抓取市场新闻标题列表"""
    news_sources = [
        {
            "name": "ABC News - Business",
            "url": "https://www.abc.net.au/news/business/",
        },
        {
            "name": "AFR",
            "url": "https://www.afr.com/",
        }
    ]
    keywords = ['asx', 'market', 'share', 'stock', 'bank', 'bhp', 'inflation', 'rba', 'china', 'oil']

    items = {}
    for source in news_sources:
        content = fetch_url(source['url'])
        if content and not content.startswith("获取网页失败"):
            extracted = _extract_lines_by_keywords(content, keywords, limit=5)
            if extracted:
                items[source["name"]] = extracted
    return items


def _fetch_market_reasons() -> str:
    """
    获取市场变动原因（大幅涨跌时使用）
    重点关注与大盘相关的新闻
    """
    # 搜索市场变动原因的关键词
    keywords = [
        "ASX 200", "ASX", "market", "index", "RBA", "interest rate",
        "inflation", "earnings", "Wall Street", "US market",
        "China", "iron ore", "Lithium", "banks"
    ]

    news_sources = [
        ("ABC News - Business", "https://www.abc.net.au/news/business/"),
        ("Reuters", "https://www.reuters.com/finance/"),
    ]

    reasons = _fetch_market_reason_items(news_sources, keywords)
    if reasons:
        return "\n".join(f"- {r}" for r in reasons[:3])
    return "暂无明确的市场变动原因"


def _fetch_market_reason_items(
    news_sources: list[tuple[str, str]] | None = None,
    keywords: list[str] | None = None
) -> list[str]:
    """抓取与市场驱动相关的标题"""
    news_sources = news_sources or [
        ("ABC News - Business", "https://www.abc.net.au/news/business/"),
        ("Reuters", "https://www.reuters.com/finance/"),
    ]
    keywords = keywords or [
        "ASX 200", "ASX", "market", "index", "RBA", "interest rate",
        "inflation", "earnings", "Wall Street", "US market",
        "China", "iron ore", "Lithium", "banks"
    ]

    reasons = []
    for name, url in news_sources:
        try:
            content = fetch_url(url)
            if content and not content.startswith("获取网页失败"):
                for line in _extract_lines_by_keywords(content, keywords, limit=3):
                    if line not in reasons:
                        reasons.append(line)
                if len(reasons) >= 3:
                    break
        except Exception as e:
            print(f"        ⚠️  {name} 获取失败: {e}")
    return reasons


def _get_real_time_data_from_web() -> str:
    """
    备用方案：通过网页抓取获取数据
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🌐 正在从网页获取实时市场数据...")

    context_parts = []

    # 定义要抓取的权威财经网站
    sources = [
        {
            "name": "ABC News - Business",
            "url": "https://www.abc.net.au/news/business/",
            "description": "ABC财经新闻"
        },
        {
            "name": "SBS News - Business",
            "url": "https://www.sbs.com.au/news/topic/business",
            "description": "SBS财经新闻"
        }
    ]

    # 抓取各个来源
    for source in sources:
        print(f"    📥 抓取: {source['name']}")
        content = fetch_url(source['url'])

        if content and not content.startswith("获取网页失败"):
            # 智能提取新闻内容
            lines = content.split('\n')
            news_items = []
            for line in lines:
                line = line.strip()
                # 跳过导航和菜单
                if any(skip in line for skip in ['MENU', 'Skip to', 'Login', 'Subscribe', '***', '---', '|||']):
                    continue
                # 保留看起来像新闻标题的行
                if 20 < len(line) < 200 and not line.startswith('['):
                    news_items.append(line)
                if len(news_items) >= 10:
                    break

            if news_items:
                context_parts.append(f"""
## {source['name']}

{chr(10).join(f'- {item}' for item in news_items[:10])}

---
""")

    # 如果抓取失败，返回空字符串
    if not context_parts:
        print("    ⚠️  无法获取实时数据，将返回空结果")
        return ""

    result = "\n".join(context_parts)
    print(f"    ✅ 已获取 {len(context_parts)} 个数据源")

    return result


def _build_market_snapshot() -> dict:
    """抓取并整理规则引擎所需的市场快照"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🌐 正在获取实时市场数据...")
    index_quote = _fetch_yahoo_finance_quote_data("%5EAXJO", "S&P/ASX 200")
    history = _fetch_yahoo_chart_data("%5EAXJO")
    stock_quotes = [quote for quote in _fetch_key_stock_quotes() if quote["price"] is not None]
    news_items_by_source = _fetch_market_news_items()
    news_items = []
    for items in news_items_by_source.values():
        news_items.extend(items)
    reasons = _fetch_market_reason_items()

    closes = [point["close"] for point in history]
    daily_returns = []
    for previous, current in zip(closes, closes[1:]):
        change_pct = _safe_pct_change(current, previous)
        if change_pct is not None:
            daily_returns.append(change_pct)

    last_close = closes[-1] if closes else index_quote["price"]
    weekly_base = closes[-6] if len(closes) >= 6 else (closes[0] if closes else index_quote["prev_close"])
    monthly_base = closes[0] if closes else index_quote["prev_close"]
    weekly_return = _safe_pct_change(last_close, weekly_base)
    monthly_return = _safe_pct_change(last_close, monthly_base)
    volatility = statistics.pstdev(daily_returns[-10:]) if len(daily_returns) >= 2 else 0.0

    recent_volumes = [point["volume"] for point in history if point["volume"] is not None]
    current_volume = recent_volumes[-1] if recent_volumes else index_quote["volume"]
    recent_avg_volume = statistics.mean(recent_volumes[-5:]) if len(recent_volumes) >= 5 else current_volume
    previous_avg_volume = statistics.mean(recent_volumes[-10:-5]) if len(recent_volumes) >= 10 else recent_avg_volume
    volume_change_pct = _safe_pct_change(recent_avg_volume, previous_avg_volume)

    return {
        "asx200": index_quote,
        "history": history,
        "key_stocks": stock_quotes,
        "news_items": news_items,
        "reason_items": reasons,
        "weekly_return": weekly_return,
        "monthly_return": monthly_return,
        "volatility": volatility,
        "current_volume": current_volume,
        "recent_avg_volume": recent_avg_volume,
        "volume_change_pct": volume_change_pct,
        "generated_at": datetime.now(),
    }


def _classify_market_regime(snapshot: dict) -> str:
    """按阈值判断市场状态"""
    weekly_return = snapshot.get("weekly_return") or 0
    monthly_return = snapshot.get("monthly_return") or 0
    volatility = snapshot.get("volatility") or 0
    volume_change = snapshot.get("volume_change_pct") or 0

    if weekly_return >= 1.5 and monthly_return >= 3.0 and volume_change >= 5:
        return "risk-on"
    if weekly_return <= -1.5 and monthly_return <= -3.0 and volume_change >= 5:
        return "risk-off"
    if abs(weekly_return) < 1.0 and abs(monthly_return) < 2.0 and volatility < 0.8:
        return "区间震荡"
    if volatility >= 1.4 or abs(volume_change) >= 15:
        return "高波动轮动"
    return "结构分化"


def _describe_volume_change(volume_change_pct: float | None) -> str:
    """描述成交量变化"""
    if volume_change_pct is None:
        return "成交量暂无可比数据"
    if volume_change_pct >= 12:
        return f"近5个交易日均量较前一阶段放大{volume_change_pct:.1f}%"
    if volume_change_pct <= -12:
        return f"近5个交易日均量较前一阶段回落{abs(volume_change_pct):.1f}%"
    return f"近5个交易日均量变化温和（{volume_change_pct:+.1f}%）"


def _stock_news_hits(stock: dict, news_items: list[str]) -> int:
    """统计个股与新闻的命中次数"""
    keywords = STOCK_KEYWORDS.get(stock["code"], [])
    mentions = 0
    for item in news_items:
        item_lower = item.lower()
        if any(keyword in item_lower for keyword in keywords):
            mentions += 1
    return mentions


def _rank_focus_stocks(snapshot: dict, limit: int = 3) -> list[dict]:
    """按涨跌幅、新闻命中和量化异常挑选重点个股"""
    ranked = []
    market_return = snapshot.get("weekly_return") or 0
    all_volumes = [stock["volume"] for stock in snapshot["key_stocks"] if stock.get("volume")]
    median_volume = statistics.median(all_volumes) if all_volumes else 0

    for stock in snapshot["key_stocks"]:
        change_pct = stock.get("change_pct") or 0
        news_hits = _stock_news_hits(stock, snapshot["news_items"])
        volume_score = 1 if median_volume and (stock.get("volume") or 0) >= median_volume else 0
        relative_score = 1 if change_pct * market_return < 0 else 0
        score = abs(change_pct) * 2 + news_hits * 1.5 + volume_score + relative_score
        ranked.append((score, abs(change_pct), stock["code"], news_hits, stock))

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [item[-1] for item in ranked[:limit]]


def _generate_market_overview(snapshot: dict) -> str:
    """生成确定性的市场概况文本"""
    index_quote = snapshot["asx200"]
    regime = _classify_market_regime(snapshot)
    weekly_return = snapshot.get("weekly_return")
    monthly_return = snapshot.get("monthly_return")
    volatility = snapshot.get("volatility") or 0
    volume_text = _describe_volume_change(snapshot.get("volume_change_pct"))

    top_gainer = max(snapshot["key_stocks"], key=lambda stock: stock.get("change_pct") or float("-inf"), default=None)
    top_loser = min(snapshot["key_stocks"], key=lambda stock: stock.get("change_pct") or float("inf"), default=None)
    reason_text = "；".join(snapshot["reason_items"][:2]) if snapshot["reason_items"] else "本周驱动主要来自指数涨跌与权重股轮动"

    lines = [
        f"ASX 200最新报 {_format_price(index_quote['price'])} 点，单日 {_format_pct(index_quote['change_pct'])}；过去5个交易日 {_format_pct(weekly_return)}，过去1个月 {_format_pct(monthly_return)}。",
        f"规则判断当前市场处于“{regime}”状态；近10个交易日波动率约 {volatility:.2f}%，{volume_text}。",
        f"本周主要驱动：{reason_text}。",
    ]

    notable_moves = []
    if top_gainer and top_gainer.get("change_pct") is not None:
        notable_moves.append(f"{top_gainer['code']} 领涨 {_format_pct(top_gainer['change_pct'])}")
    if top_loser and top_loser.get("change_pct") is not None and (not top_gainer or top_loser["code"] != top_gainer["code"]):
        notable_moves.append(f"{top_loser['code']} 领跌 {_format_pct(top_loser['change_pct'])}")
    if notable_moves:
        lines.append("值得注意的个股异动：" + "，".join(notable_moves) + "。")

    return "\n\n".join(lines)


def _generate_stock_analysis(snapshot: dict) -> str:
    """生成确定性的个股分析文本"""
    focus_stocks = _rank_focus_stocks(snapshot)
    if not focus_stocks:
        return "暂无可用个股数据。"

    market_return = snapshot.get("weekly_return") or 0
    sections = []
    for stock in focus_stocks:
        change_pct = stock.get("change_pct") or 0
        news_hits = _stock_news_hits(stock, snapshot["news_items"])
        if news_hits:
            catalyst = f"相关主题在抓取新闻中出现 {news_hits} 次"
        elif change_pct > 0 and market_return < 0:
            catalyst = "逆势跑赢大盘，说明资金偏向防御或主题催化"
        elif change_pct < 0 and market_return > 0:
            catalyst = "明显落后于指数，短线承压更突出"
        else:
            catalyst = "价格变动主要来自板块轮动与仓位再平衡"

        sections.append(
            f"**{stock['code']} ({stock['name']})** — 日内波动位居样本前列\n"
            f"涨跌幅 {_format_pct(stock.get('change_pct'))}，最新价 ${_format_price(stock.get('price'))}，成交量 {stock.get('volume') or 'N/A'}。\n"
            f"触发逻辑：{catalyst}；若同方向波动延续，下一周更容易成为资金继续验证的对象。"
        )

    return "\n\n".join(sections)


def _generate_investment_calendar(snapshot: dict, lookahead_days: int = 14) -> str:
    """基于固定事件规则生成未来两周日历"""
    today = snapshot["generated_at"].date()
    window_end = today + timedelta(days=lookahead_days)
    events = []

    for month_offset in range(2):
        month_anchor = today.replace(day=1)
        probe_month = month_anchor.month + month_offset
        probe_year = month_anchor.year + ((probe_month - 1) // 12)
        probe_month = ((probe_month - 1) % 12) + 1

        for rule in EVENT_RULES:
            event_dt = _nth_weekday_of_month(probe_year, probe_month, rule["weekday"], rule["occurrence"])
            if not event_dt:
                continue
            event_date = event_dt.date()
            if today <= event_date <= window_end:
                events.append((event_date, rule["name"], rule["impact"]))

    if today.month in (1, 2, 4, 7, 10):
        earnings_date = today + timedelta(days=7)
        if earnings_date <= window_end:
            events.append((earnings_date, "财报与经营更新窗口", "资源、银行与消费龙头更容易出现业绩驱动波动"))

    events = sorted(set(events), key=lambda item: item[0])[:8]
    if not events:
        return "- **未来两周** - 暂无固定高频宏观事件，重点关注指数波动和权重股公告。"

    return "\n".join(
        f"- **{event_date.month}月{event_date.day}日** - {name}，{impact}"
        for event_date, name, impact in events
    )


def _generate_risk_alert(snapshot: dict) -> str:
    """基于波动、成交量和事件规则生成风险提示"""
    alerts = []
    weekly_return = snapshot.get("weekly_return") or 0
    volatility = snapshot.get("volatility") or 0
    volume_change = snapshot.get("volume_change_pct") or 0
    upcoming_events = _generate_investment_calendar(snapshot).splitlines()

    if volatility >= 1.4:
        alerts.append(
            f"- **波动率抬升风险**：近10个交易日波动率已升至 {volatility:.2f}%。若接下来宏观数据偏离预期，ASX 200短线波动可能继续放大。"
        )
    if weekly_return <= -1.5 and volume_change >= 5:
        alerts.append(
            f"- **放量下跌风险**：指数近5个交易日回报为 {_format_pct(weekly_return)}，同时量能变化 {volume_change:+.1f}%。这通常代表避险交易升温，银行和资源股回撤压力更大。"
        )
    if upcoming_events:
        first_event = upcoming_events[0].lstrip("- ").replace("**", "")
        alerts.append(
            f"- **事件前重定价风险**：即将到来的 {first_event}。若结果与市场预期偏离，利率敏感与高估值板块最容易先出现价格重定价。"
        )
    if not alerts:
        alerts.append("- **当前无特殊风险事件**：波动率与成交量均未触发高风险阈值，短线更像常规区间波动。")

    return "\n".join(alerts[:3])


def markdown_to_html(text: str) -> str:
    """
    将简单的Markdown格式转换为HTML

    Args:
        text: Markdown格式的文本

    Returns:
        HTML格式的文本
    """
    if not text:
        return ""

    html = text

    # 处理代码块（```...```）
    html = re.sub(r'```(\w*)\n(.*?)\n```', r'<pre><code>\2</code></pre>', html, flags=re.DOTALL)

    # 处理行内代码（`...`）
    html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)

    # 处理标题（###, ##, #）
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

    # 处理粗体（**text**）
    html = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', html)

    # 处理分隔线（--- 或 ***）
    html = re.sub(r'^[\-\*]{3,}$', r'<hr>', html, flags=re.MULTILINE)

    # 处理表格（| 分隔）
    lines = html.split('\n')
    in_table = False
    table_rows = []
    result_lines = []

    for line in lines:
        if '|' in line and line.strip().startswith('|'):
            if not in_table:
                in_table = True
                table_rows = []
            cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
            table_rows.append(cells)
        else:
            if in_table:
                if table_rows:
                    result_lines.append('<table>')
                    for i, row in enumerate(table_rows):
                        if i == 0:
                            result_lines.append('<thead><tr>')
                            for cell in row:
                                result_lines.append(f'<th>{cell}</th>')
                            result_lines.append('</tr></thead><tbody>')
                        elif i == 1:
                            continue
                        else:
                            result_lines.append('<tr>')
                            for cell in row:
                                result_lines.append(f'<td>{cell}</td>')
                            result_lines.append('</tr>')
                    result_lines.append('</tbody></table>')
                table_rows = []
                in_table = False
            result_lines.append(line)

    if in_table and table_rows:
        result_lines.append('<table>')
        for i, row in enumerate(table_rows):
            if i == 0:
                result_lines.append('<thead><tr>')
                for cell in row:
                    result_lines.append(f'<th>{cell}</th>')
                result_lines.append('</tr></thead><tbody>')
            elif i == 1:
                continue
            else:
                result_lines.append('<tr>')
                for cell in row:
                    result_lines.append(f'<td>{cell}</td>')
                result_lines.append('</tr>')
        result_lines.append('</tbody></table>')

    html = '\n'.join(result_lines)

    # 处理列表 - 支持嵌套和缩进
    lines = html.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 检测列表项（以*、-或数字+点开头，可能有缩进）
        list_match = re.match(r'^(\s*)([\*\-]|\d+\.)\s+(.+)$', line)

        if list_match:
            indent = len(list_match.group(1))
            marker = list_match.group(2)
            content = list_match.group(3)

            # 确定列表类型和嵌套层级
            is_ordered = marker.endswith('.')
            base_indent = indent // 4  # 每4个空格一级嵌套

            # 收集连续的列表项
            list_items = []
            list_level = base_indent
            i += 1

            while i < len(lines):
                next_line = lines[i]
                next_match = re.match(r'^(\s*)([\*\-]|\d+\.)\s+(.+)$', next_line)

                if next_match:
                    next_indent = len(next_match.group(1)) // 4
                    next_content = next_match.group(3)

                    # 如果缩进更深层，开始嵌套列表
                    if next_indent > list_level:
                        # 处理嵌套
                        nested_items = [next_content]
                        i += 1
                        nested_level = next_indent

                        while i < len(lines):
                            nested_line = lines[i]
                            nested_match = re.match(r'^(\s*)([\*\-]|\d+\.)\s+(.+)$', nested_line)

                            if nested_match:
                                curr_indent = len(nested_match.group(1)) // 4
                                curr_content = nested_match.group(3)

                                if curr_indent >= nested_level:
                                    nested_items.append(curr_content)
                                    i += 1
                                else:
                                    break
                            else:
                                break

                        # 生成嵌套列表
                        nested_html = '<ul>' if not next_match.group(2).endswith('.') else '<ol>'
                        for item in nested_items:
                            nested_html += f'<li>{item}</li>'
                        nested_html += '</ul>'
                        list_items.append(nested_html)
                        continue
                    elif next_indent < list_level:
                        # 列表层级结束
                        break
                    else:
                        list_items.append(next_content)
                        i += 1
                else:
                    # 非列表行，结束当前列表
                    break

            # 生成列表HTML
            if is_ordered:
                list_html = '<ol>'
            else:
                list_html = '<ul>'

            for item in list_items:
                if '<ul>' in item or '<ol>' in item:
                    list_html += f'<li>{item}</li>'
                else:
                    # 移除粗体标记前缀（如 "**驱动因素：**"）
                    item = re.sub(r'^\*\*([^*]+)\*\*:\s*', r'<strong>\1:</strong> ', item)
                    list_html += f'<li>{item}</li>'

            if is_ordered:
                list_html += '</ol>'
            else:
                list_html += '</ul>'

            result.append(list_html)
        else:
            result.append(line)
            i += 1

    html = '\n'.join(result)

    # 处理段落
    lines = html.split('\n')
    result = []
    in_paragraph = False
    paragraph_lines = []

    for line in lines:
        stripped = line.strip()

        # 跳过空行
        if not stripped:
            if in_paragraph and paragraph_lines:
                paragraph_text = ' '.join(paragraph_lines)
                # 移除段落开头的粗体标记前缀
                paragraph_text = re.sub(r'^\*\*([^*]+)\*\*:\s*', r'<strong>\1:</strong> ', paragraph_text)
                result.append(f'<p>{paragraph_text}</p>')
                paragraph_lines = []
                in_paragraph = False
            continue

        # HTML标签行直接添加
        if stripped.startswith('<'):
            if in_paragraph and paragraph_lines:
                paragraph_text = ' '.join(paragraph_lines)
                paragraph_text = re.sub(r'^\*\*([^*]+)\*\*:\s*', r'<strong>\1:</strong> ', paragraph_text)
                result.append(f'<p>{paragraph_text}</p>')
                paragraph_lines = []
                in_paragraph = False
            result.append(stripped)
        else:
            # 普通文本行
            paragraph_lines.append(stripped)
            in_paragraph = True

    if in_paragraph and paragraph_lines:
        paragraph_text = ' '.join(paragraph_lines)
        paragraph_text = re.sub(r'^\*\*([^*]+)\*\*:\s*', r'<strong>\1:</strong> ', paragraph_text)
        result.append(f'<p>{paragraph_text}</p>')

    html = '\n'.join(result)

    return html


def generate_market_research() -> dict:
    """
    使用确定性规则生成完整的周报内容

    Returns:
        包含各部分内容的字典
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始生成确定性周报...")
    snapshot = _build_market_snapshot()

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在生成市场概况...")
    market_overview = _generate_market_overview(snapshot)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在生成个股分析...")
    stock_analysis = _generate_stock_analysis(snapshot)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在生成投资日历...")
    investment_calendar = _generate_investment_calendar(snapshot)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在生成风险提示...")
    risk_alert = _generate_risk_alert(snapshot)

    return {
        "market_overview": market_overview,
        "stock_analysis": stock_analysis,
        "investment_calendar": investment_calendar,
        "risk_alert": risk_alert,
    }


def generate_asx_chart() -> str:
    """
    生成ASX 200过去1个月的走势图

    Returns:
        Base64编码的PNG图片数据URL
    """
    try:
        import matplotlib
        matplotlib.use('Agg')  # 使用非交互式后端
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from io import BytesIO
        import base64

        print("    📈 生成ASX 200走势图...")

        # 获取过去1个月的数据
        end_date = datetime.now()
        start_date = end_date - timedelta(days=35)  # 多获取几天以确保有足够的交易日

        # 构建Yahoo Finance图表URL
        # 使用Historical Data API
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/%5EAXJO"
        params = {
            "period1": int(start_date.timestamp()),
            "period2": int(end_date.timestamp()),
            "interval": "1d",
        }

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }

        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            print("        ⚠️  无法获取图表数据")
            return ""

        data = response.json()

        # 解析数据
        result = data.get("chart", {}).get("result", [])
        if not result:
            print("        ⚠️  图表数据为空")
            return ""

        timestamps = result[0].get("timestamp", [])
        closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])

        if not timestamps or not closes:
            print("        ⚠️  无法解析价格数据")
            return ""

        # 过滤空值
        valid_data = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
        if len(valid_data) < 5:
            print("        ⚠️  有效数据不足")
            return ""

        dates = [datetime.fromtimestamp(t) for t, _ in valid_data]
        prices = [c for _, c in valid_data]

        # 生成图表
        plt.figure(figsize=(10, 4))
        plt.plot(dates, prices, linewidth=2, color='#007AFF')
        plt.fill_between(dates, prices, alpha=0.1, color='#007AFF')

        # 设置标题和标签
        current_price = prices[-1]
        change = prices[-1] - prices[0]
        change_pct = (change / prices[0]) * 100

        title = f"ASX 200 - Past 1 Month | Current: {current_price:.2f} ({change:+.2f}, {change_pct:+.2f}%)"
        plt.title(title, fontsize=12, fontweight='bold')
        plt.ylabel('Index Level', fontsize=10)

        # 格式化x轴
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
        try:
            plt.gca().xaxis.set_major_locator(mdates.WeekdayLocator(by=mdates.MO))
        except TypeError:
            # 旧版本matplotlib兼容
            plt.gca().xaxis.set_major_locator(mdates.DayLocator(interval=7))
        plt.xticks(rotation=45)

        # 添加网格
        plt.grid(True, alpha=0.3, linestyle='--')
        plt.tight_layout()

        # 保存为base64图片
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode()
        plt.close()

        print(f"    ✅ 图表生成成功 (数据点: {len(dates)})")
        return f"data:image/png;base64,{image_base64}"

    except ImportError:
        print("        ⚠️  matplotlib未安装，无法生成图表")
        return ""
    except Exception as e:
        print(f"        ⚠️  图表生成失败: {e}")
        return ""


def generate_report_content(research_data: dict) -> str:
    """
    生成完整的周报HTML内容

    Args:
        research_data: 调研数据字典

    Returns:
        HTML格式的报告内容
    """
    now = datetime.now()
    report_date = now.strftime("%Y年%m月%d日")
    week_number = now.isocalendar()[1]

    # 生成走势图
    chart_url = generate_asx_chart()
    chart_html = ""
    if chart_url:
        chart_html = f'<div style="margin: 12px 0;"><img src="{chart_url}" alt="ASX 200 走势" style="max-width:100%;"></div>'

    # 转换Markdown为HTML
    market_overview_html = markdown_to_html(research_data.get('market_overview', '暂无数据'))
    stock_analysis_html = markdown_to_html(research_data.get('stock_analysis', '暂无数据'))
    investment_calendar_html = markdown_to_html(research_data.get('investment_calendar', '暂无数据'))
    risk_alert_html = markdown_to_html(research_data.get('risk_alert', '暂无数据'))

    html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ASX市场简报 - {report_date}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
            line-height: 1.7;
            color: #1a1a1a;
            max-width: 640px;
            margin: 0 auto;
            padding: 0;
            background-color: #ffffff;
        }}
        .container {{
            padding: 32px 24px;
        }}
        .header {{
            padding-bottom: 16px;
            margin-bottom: 24px;
            border-bottom: 1px solid #e0e0e0;
        }}
        .header h1 {{
            color: #1a1a1a;
            margin: 0 0 4px 0;
            font-size: 22px;
            font-weight: 700;
            letter-spacing: -0.3px;
        }}
        .header .date {{
            color: #888;
            font-size: 13px;
        }}
        .section {{
            margin-bottom: 28px;
        }}
        .section-title {{
            color: #1a1a1a;
            font-size: 15px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 12px;
            padding-bottom: 6px;
            border-bottom: 2px solid #1a1a1a;
            display: inline-block;
        }}
        .section-body {{
            font-size: 15px;
            line-height: 1.7;
            color: #333;
        }}
        .section-body h1, .section-body h2, .section-body h3 {{
            color: #1a1a1a;
            font-size: 16px;
            font-weight: 600;
            margin: 16px 0 6px 0;
        }}
        .section-body h1 {{ font-size: 17px; }}
        .section-body p {{
            margin: 8px 0;
        }}
        .section-body ul, .section-body ol {{
            margin: 8px 0;
            padding-left: 20px;
        }}
        .section-body li {{
            margin: 4px 0;
        }}
        .section-body strong {{
            color: #1a1a1a;
            font-weight: 600;
        }}
        .section-body table {{
            width: 100%;
            border-collapse: collapse;
            margin: 12px 0;
            font-size: 14px;
        }}
        .section-body table th {{
            background-color: #f5f5f5;
            color: #1a1a1a;
            padding: 8px 10px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #ddd;
        }}
        .section-body table td {{
            padding: 8px 10px;
            border-bottom: 1px solid #eee;
        }}
        .section-body hr {{
            border: none;
            border-top: 1px solid #eee;
            margin: 16px 0;
        }}
        .section-body code {{
            background-color: #f5f5f5;
            padding: 1px 4px;
            border-radius: 3px;
            font-size: 13px;
        }}
        .divider {{
            border: none;
            border-top: 1px solid #eee;
            margin: 0;
        }}
        .footer {{
            margin-top: 28px;
            padding-top: 16px;
            border-top: 1px solid #e0e0e0;
            color: #aaa;
            font-size: 12px;
            line-height: 1.5;
        }}
        .positive {{ color: #16a34a; font-weight: 600; }}
        .negative {{ color: #dc2626; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>ASX 市场简报</h1>
            <div class="date">{report_date}</div>
        </div>

        <div class="section">
            <div class="section-title">📊 市场概况</div>
            <div class="section-body">{chart_html}{market_overview_html}</div>
        </div>

        <div class="section">
            <div class="section-title">🔍 值得关注</div>
            <div class="section-body">{stock_analysis_html}</div>
        </div>

        <div class="section">
            <div class="section-title">📅 近期事件</div>
            <div class="section-body">{investment_calendar_html}</div>
        </div>

        <div class="section">
            <div class="section-title">⚠️ 风险提示</div>
            <div class="section-body">{risk_alert_html}</div>
        </div>

        <div class="footer">
            规则引擎自动生成，仅供参考，不构成投资建议。<br>
            生成时间: {now.strftime('%Y-%m-%d %H:%M')}
        </div>
    </div>
</body>
</html>
"""
    return html_content


def send_email(report_html: str, report_date: str) -> bool:
    """
    发送周报邮件

    Args:
        report_html: HTML格式的报告内容
        report_date: 报告日期

    Returns:
        发送成功返回True，失败返回False
    """
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("错误: 未设置Gmail邮箱或应用密码")
        return False

    if not RECIPIENT_EMAIL:
        print("错误: 未设置收件人邮箱")
        return False

    try:
        # 创建邮件
        msg = MIMEMultipart('alternative')
        # 使用Header正确处理中文和emoji
        msg['Subject'] = Header(f"ASX 市场简报 - {report_date}", 'utf-8')
        msg['From'] = GMAIL_ADDRESS
        msg['To'] = RECIPIENT_EMAIL

        # 添加HTML内容
        html_part = MIMEText(report_html, 'html', 'utf-8')
        msg.attach(html_part)

        # 连接Gmail SMTP服务器
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在连接Gmail服务器...")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 邮件发送成功！")
            return True

    except Exception as e:
        print(f"发送邮件失败: {str(e)}")
        return False


def save_report_locally(report_html: str, report_date: str) -> Path:
    """
    保存报告到本地

    Args:
        report_html: HTML格式的报告内容
        report_date: 报告日期

    Returns:
        保存的文件路径
    """
    filename = f"asx_report_{datetime.now().strftime('%Y%m%d')}.html"
    filepath = OUTPUT_DIR / filename

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(report_html)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 报告已保存到: {filepath}")
    return filepath


def update_archive_index(report_filename: str) -> None:
    """
    更新归档索引页面，列出所有历史报告

    Args:
        report_filename: 新报告的文件名
    """
    index_path = OUTPUT_DIR / 'index.html'

    # 获取所有HTML报告文件（除了index.html）
    report_files = sorted(
        [f for f in OUTPUT_DIR.glob('asx_report_*.html')],
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )

    # 生成报告列表HTML
    report_list_html = ""
    for report_file in report_files:
        # 从文件名提取日期
        date_match = report_file.stem.replace('asx_report_', '')
        if len(date_match) == 8:
            try:
                date_obj = datetime.strptime(date_match, '%Y%m%d')
                display_date = date_obj.strftime('%Y年%m月%d日')
                weekday = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][date_obj.weekday()]
            except:
                display_date = date_match
                weekday = ''
        else:
            display_date = date_match
            weekday = ''

        report_list_html += f"""
        <tr>
            <td>{display_date} {weekday}</td>
            <td><a href="{report_file.name}">查看</a></td>
        </tr>
        """

    # 生成完整的index.html
    index_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ASX 市场简报 - 归档</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
            line-height: 1.6;
            color: #1a1a1a;
            max-width: 640px;
            margin: 0 auto;
            padding: 20px;
            background-color: #ffffff;
        }}
        .header {{
            padding-bottom: 16px;
            margin-bottom: 24px;
            border-bottom: 1px solid #e0e0e0;
        }}
        .header h1 {{
            color: #1a1a1a;
            margin: 0 0 4px 0;
            font-size: 22px;
            font-weight: 700;
        }}
        .header .subtitle {{
            color: #888;
            font-size: 13px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
        }}
        th {{
            background-color: #f5f5f5;
            color: #1a1a1a;
            padding: 10px 12px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #ddd;
        }}
        td {{
            padding: 10px 12px;
            border-bottom: 1px solid #eee;
        }}
        a {{
            color: #1a1a1a;
            text-decoration: underline;
        }}
        a:hover {{
            color: #555;
        }}
        .footer {{
            margin-top: 28px;
            padding-top: 16px;
            border-top: 1px solid #e0e0e0;
            color: #aaa;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>ASX 市场简报</h1>
        <div class="subtitle">历史报告归档 · {len(report_files)} 份报告</div>
    </div>

    <table>
        <thead>
            <tr>
                <th>日期</th>
                <th>查看</th>
            </tr>
        </thead>
        <tbody>
            {report_list_html}
        </tbody>
    </table>

    <div class="footer">
        规则引擎自动生成，仅供参考。<br>
        最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M')}
    </div>
</body>
</html>"""

    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(index_html)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 归档索引已更新: {index_path}")


def generate_text_summary(research_data: dict) -> str:
    """
    生成纯文本格式的摘要

    Args:
        research_data: 调研数据字典

    Returns:
        纯文本摘要
    """
    now = datetime.now()

    summary = f"""ASX 市场简报
{now.strftime('%Y年%m月%d日')}

--- 市场概况 ---
{research_data.get('market_overview', '暂无数据')}

--- 值得关注 ---
{research_data.get('stock_analysis', '暂无数据')}

--- 近期事件 ---
{research_data.get('investment_calendar', '暂无数据')}

--- 风险提示 ---
{research_data.get('risk_alert', '暂无数据')}

---
规则引擎自动生成，仅供参考，不构成投资建议。
"""
    return summary


def main():
    """主函数"""
    print("="*60)
    print("ASX 市场简报生成器")
    print("="*60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 检查配置
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("⚠️ 警告: 未设置完整Gmail配置，本次将跳过邮件发送")

    try:
        # 1. 进行市场调研
        research_data = generate_market_research()

        # 2. 生成HTML报告
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 生成报告内容...")
        report_html = generate_report_content(research_data)

        # 3. 生成纯文本摘要
        text_summary = generate_text_summary(research_data)

        # 4. 保存到本地
        report_date = datetime.now().strftime("%Y年%m月%d日")
        html_path = save_report_locally(report_html, report_date)

        # 确保.nojekyll文件存在（禁用Jekyll处理）
        nojekyll_path = OUTPUT_DIR / '.nojekyll'
        if not nojekyll_path.exists():
            nojekyll_path.touch()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 已创建.nojekyll文件")

        # 更新归档索引页面
        update_archive_index(html_path.name)

        # 保存纯文本版本
        txt_filename = f"asx_report_{datetime.now().strftime('%Y%m%d')}.txt"
        txt_path = OUTPUT_DIR / txt_filename
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(text_summary)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 纯文本版已保存到: {txt_path}")

        # 5. 发送邮件
        if GMAIL_ADDRESS and GMAIL_APP_PASSWORD and RECIPIENT_EMAIL:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 发送邮件中...")
            email_sent = send_email(report_html, report_date)

            if email_sent:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 周报生成完成！")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 周报已生成但邮件发送失败")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 周报生成完成（未配置邮件发送）")

    except Exception as e:
        print(f"❌ 发生错误: {str(e)}")
        import traceback
        traceback.print_exc()

    print()
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)


if __name__ == "__main__":
    main()
