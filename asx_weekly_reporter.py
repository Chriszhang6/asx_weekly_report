#!/usr/bin/env python3
"""
ASX Weekly Investment Report Generator
自动生成澳洲股票投资周报并发送邮件
集成WebSearch获取实时数据
"""

import os
import json
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from datetime import datetime, timedelta
from pathlib import Path
import requests
from urllib.parse import quote

# 尝试导入yfinance，用于获取真实的股市数据
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("警告: yfinance未安装，将使用简化的市场数据。请运行: pip install yfinance")

# ============== 配置区域 ==============
# 从环境变量读取配置
GMAIL_ADDRESS = os.getenv('GMAIL_ADDRESS', '')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD', '')
ZAI_API_KEY = os.getenv('ZAI_API_KEY', '')
RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL', GMAIL_ADDRESS)  # 默认发送给自己

# 清理特殊字符（非断空格等）
def clean_string(s: str) -> str:
    """清理字符串中的特殊字符"""
    if s:
        # 替换非断空格（\xa0）为普通空格，然后删除所有空格
        return s.replace('\xa0', ' ').replace(' ', '')
    return s

GMAIL_APP_PASSWORD = clean_string(GMAIL_APP_PASSWORD)

# 输出目录 - GitHub Actions使用docs目录，本地使用Downloads目录
# 检测是否在GitHub Actions环境中运行
if os.getenv('GITHUB_ACTIONS') == 'true':
    OUTPUT_DIR = Path('./docs')
else:
    OUTPUT_DIR = Path.home() / 'Downloads' / 'asx_weekly_report'
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

# Z.ai GLM API配置 - 使用 Anthropic 兼容端点
ZAI_API_URL = "https://api.z.ai/api/anthropic/v1/messages"


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

        if asx200_data:
            market_data = f"""
## 📊 S&P/ASX 200 指数表现 ({current_date})

{asx200_data}

"""
            context_parts.append(market_data)
            print(f"    ✅ ASX 200数据已获取")

        # ========== 2. 获取热门个股数据 ==========
        print("    📊 获取热门个股...")
        popular_stocks = {
            "BHP": "BHP.AX",
            "CBA": "CBA.AX",
            "RIO": "RIO.AX",
            "CSL": "CSL.AX",
            "MQG": "MQG.AX",
            "WBC": "WBC.AX",
        }

        stock_data = "## 🔥 热门个股表现\n\n"
        for name, ticker in popular_stocks.items():
            stock_info = _fetch_yahoo_finance_data(ticker)
            if stock_info:
                stock_data += f"### {name}\n{stock_info}\n"
            # 添加小延迟避免请求过快
            import time
            time.sleep(0.5)

        context_parts.append(stock_data)
        print("    ✅ 个股数据获取完成")

        # ========== 3. 获取市场新闻 ==========
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


def _fetch_yahoo_finance_data(ticker_symbol: str) -> str:
    """
    从Yahoo Finance HTML页面抓取股票/指数数据

    Args:
        ticker_symbol: 股票代码，如 "^AXJO" 或 "BHP.AX"

    Returns:
        格式化的股票数据文本
    """
    try:
        # 构建Yahoo Finance URL
        # 对于带^的符号需要URL编码
        if ticker_symbol.startswith('%5E'):
            url = f"https://au.finance.yahoo.com/quote/{ticker_symbol}"
        else:
            url = f"https://au.finance.yahoo.com/quote/{ticker_symbol}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-AU,en;q=0.9',
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            return f"⚠️ 无法获取数据 (HTTP {response.status_code})"

        content = response.text

        # 从HTML中提取JSON数据
        # Yahoo Finance在页面中嵌入了一个包含所有数据的JSON对象
        import json

        # 尝试多种方式提取数据
        patterns = [
            r'"regularMarketPrice":\s*\{[^}]*"raw":\s*([\d.]+)',
            r'"price":\s*([\d.]+)',
        ]

        price = None
        change = None
        change_pct = None
        prev_close = None
        high = None
        low = None
        volume = None

        # 提取当前价格
        price_match = re.search(r'"regularMarketPrice":\s*\{[^}]*"raw":\s*([\d.]+)', content)
        if price_match:
            price = float(price_match.group(1))

        # 提取前收盘价
        prev_match = re.search(r'"regularMarketPreviousClose":\s*\{[^}]*"raw":\s*([\d.]+)', content)
        if prev_match:
            prev_close = float(prev_match.group(1))

        # 提取涨跌额
        change_match = re.search(r'"regularMarketChange":\s*\{[^}]*"raw":\s*([-\d.]+)', content)
        if change_match:
            change = float(change_match.group(1))

        # 提取涨跌幅
        change_pct_match = re.search(r'"regularMarketChangePercent":\s*\{[^}]*"raw":\s*([-\d.]+)', content)
        if change_pct_match:
            change_pct = float(change_pct_match.group(1))

        # 提取最高价
        high_match = re.search(r'"regularMarketDayHigh":\s*\{[^}]*"raw":\s*([\d.]+)', content)
        if high_match:
            high = float(high_match.group(1))

        # 提取最低价
        low_match = re.search(r'"regularMarketDayLow":\s*\{[^}]*"raw":\s*([\d.]+)', content)
        if low_match:
            low = float(low_match.group(1))

        # 提取成交量
        vol_match = re.search(r'"regularMarketVolume":\s*\{[^}]*"raw":\s*(\d+)', content)
        if vol_match:
            volume = int(vol_match.group(1))

        # 格式化输出
        if price is not None:
            result = f"- **当前价格**: {price:.2f}\n"

            if change is not None:
                result += f"- **涨跌额**: {change:+.2f}\n"

            if change_pct is not None:
                result += f"- **涨跌幅**: {change_pct:+.2f}%\n"

            if prev_close is not None:
                result += f"- **前收盘**: {prev_close:.2f}\n"

            if high is not None:
                result += f"- **今日最高**: {high:.2f}\n"

            if low is not None:
                result += f"- **今日最低**: {low:.2f}\n"

            if volume is not None and volume > 0:
                result += f"- **成交量**: {volume:,}\n"

            return result
        else:
            return f"⚠️ 无法解析价格数据"

    except Exception as e:
        return f"⚠️ 获取失败: {str(e)}"


def _fetch_market_news() -> str:
    """
    获取市场新闻（辅助函数）
    """
    news_sources = [
        {
            "name": "ABC News - Business",
            "url": "https://www.abc.net.au/news/business/",
            "description": "ABC财经新闻"
        },
        {
            "name": "AFR",
            "url": "https://www.afr.com/",
            "description": "澳洲金融评论"
        }
    ]

    news_parts = []
    for source in news_sources:
        content = fetch_url(source['url'])
        if content and not content.startswith("获取网页失败"):
            # 提取标题和新闻内容（更智能的提取）
            lines = content.split('\n')
            news_items = []
            for i, line in enumerate(lines):
                # 跳过导航和菜单
                if any(skip in line for skip in ['MENU', 'Skip to', 'Login', 'Subscribe', '***', '---']):
                    continue
                # 保留看起来像新闻标题的行
                if len(line.strip()) > 20 and len(line.strip()) < 200:
                    if any(keyword in line.lower() for keyword in ['asx', 'market', 'share', 'stock', 'bank', 'bhp', 'inflation', 'rba']):
                        news_items.append(line.strip())
                if len(news_items) >= 5:  # 最多取5条
                    break

            if news_items:
                news_parts.append(f"### {source['name']}\n\n" + "\n".join(f"- {item}" for item in news_items))

    if news_parts:
        return "## 📰 市场新闻\n\n" + "\n\n".join(news_parts)
    return ""


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
        print("    ⚠️  无法获取实时数据，将使用模型预训练知识")
        return ""

    result = "\n".join(context_parts)
    print(f"    ✅ 已获取 {len(context_parts)} 个数据源")

    return result


def search_web_simulated(query: str) -> list:
    """
    模拟网络搜索（使用Google搜索通过serpapi或其他API）

    注意：这是一个框架函数。要实现真正的搜索功能，你需要：
    1. 注册搜索API服务（如SerpApi、Google Custom Search API）
    2. 将API密钥添加到环境变量
    3. 在此函数中调用API

    Args:
        query: 搜索关键词

    Returns:
        搜索结果列表
    """
    # 这里是搜索API的框架
    # 你可以集成以下服务：
    #
    # SerpApi: https://serpapi.com/google-search
    # Google Custom Search API: https://developers.google.com/custom-search
    # Bing Search API: https://www.microsoft.com/cognitive-services/bing-news-search-api

    # 示例代码（需要SERPAPI_KEY环境变量）:
    # api_key = os.getenv('SERPAPI_KEY')
    # if api_key:
    #     url = f"https://serpapi.com/search?q={quote(query)}&location=Australia&hl=en&gl=au&api_key={api_key}"
    #     response = requests.get(url)
    #     return response.json().get('organic_results', [])

    return []


def call_zai_api(prompt: str, context: str = "", model: str = "glm-4.7") -> str:
    """
    调用Z.ai GLM API进行市场调研（使用Anthropic兼容端点）

    Args:
        prompt: 提示词
        context: 实时数据上下文（可选）
        model: 模型名称，默认使用glm-4.7

    Returns:
        API返回的响应文本
    """
    if not ZAI_API_KEY:
        return "错误: 未设置ZAI_API_KEY环境变量"

    # 如果有实时上下文，将其添加到prompt中
    full_prompt = prompt
    if context and context.strip():
        full_prompt = f"""# 实时市场数据背景

以下是最新的市场数据和分析（获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}）：

{context}

---

# 分析任务

{prompt}

请基于上述实时数据进行分析。如果某些信息在背景数据中没有提到，请说明"根据现有信息无法确认"。
"""

    headers = {
        "x-api-key": ZAI_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "max_tokens": 4000,
        "messages": [
            {
                "role": "user",
                "content": full_prompt
            }
        ]
    }

    try:
        response = requests.post(ZAI_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()

        # 提取回复内容（Anthropic API格式）
        if 'content' in result and len(result['content']) > 0:
            return result['content'][0]['text']
        else:
            return f"API响应格式异常: {result}"

    except requests.exceptions.RequestException as e:
        return f"API调用失败: {str(e)}"
    except Exception as e:
        return f"处理响应时出错: {str(e)}"


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
    使用AI进行市场调研，生成完整的周报内容

    Returns:
        包含各部分内容的字典
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始市场调研...")

    # ============== 首先获取实时数据 ==============
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🌐 正在获取实时市场数据...")

    # 方法1：尝试抓取财经网站
    try:
        realtime_context = get_real_time_data()
    except Exception as e:
        print(f"    ⚠️  网页抓取失败: {e}")
        realtime_context = ""

    # 方法2：如果抓取失败，使用搜索API（需要配置）
    if not realtime_context or realtime_context.strip() == "":
        print(f"    📡 尝试使用搜索API...")
        try:
            # 这里可以集成搜索API
            # 例如使用SerpApi或其他搜索服务
            search_results = search_web_simulated("ASX 200 market news this week")
            if search_results:
                realtime_context = "搜索结果:\n"
                for result in search_results[:5]:
                    realtime_context += f"- {result.get('title', '')}\n"
        except Exception as e:
            print(f"    ⚠️  搜索失败: {e}")
            realtime_context = ""

    # 如果都没有获取到实时数据，提示用户
    if not realtime_context or realtime_context.strip() == "":
        print(f"    ⚠️  无法获取实时数据，将使用模型预训练知识")
        print(f"    💡 建议: 集成搜索API或数据源以获得更准确的分析")
        realtime_context = ""

    # ============== 使用LLM分析数据 ==============

    # 第一部分：市场整体概况
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在分析ASX市场整体概况...")
    market_overview_prompt = """你是专业的澳洲股市分析师。请分析本周澳洲股市(ASX)的整体表现，包括：

1. S&P/ASX 200指数表现
2. 主要板块涨跌幅
3. 市场情绪和关键事件
4. 宏观经济环境（利率、通胀等）

请用中文回复，内容要专业、简洁，包含具体数字。今天是{current_date}。"""

    market_overview = call_zai_api(market_overview_prompt, realtime_context)

    # 第二部分：券商最新推荐
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在获取券商最新推荐...")
    broker_recommendations_prompt = """你是澳洲股市研究专家。请提供本周澳洲券商（如Bell Potter、Morgans、Macquarie、Goldman Sachs等）的最新股票推荐，包括：

1. 新获得买入评级的ASX股票
2. 券商目标价调整
3. 推荐理由摘要

请用中文回复，重点关注意2026年2月的最新推荐。格式如下：
股票代码 | 公司名称 | 券商 | 评级 | 目标价 | 核心理由"""

    broker_recommendations = call_zai_api(broker_recommendations_prompt, realtime_context)

    # 第三部分：热门板块分析
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在分析热门板块...")
    sector_analysis_prompt = """你是澳洲股市板块分析专家。请分析本周ASX热门板块的表现和前景，重点关注：

1. 矿业/资源板块（铁矿、锂矿、稀土、铀矿）
2. 科技板块
3. 银行板块
4. 医疗健康板块
5. 消费/零售板块

每个板块请包含：
- 本周表现
- 驱动因素
- 代表性股票
- 未来展望

请用中文回复，数据准确。"""

    sector_analysis = call_zai_api(sector_analysis_prompt, realtime_context)

    # 第四部分：个股深度分析
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在进行个股深度分析...")
    stock_analysis_prompt = """你是澳洲股市个股分析专家。请根据本周市场动态，自主挑选3-5只最值得关注的ASX股票进行深度分析。

**选股标准：**
1. 基于上述实时数据中的市场热点和新闻
2. 本周有重要动态（财报、公告、重大事件等）的股票
3. 券商评级有重要调整的股票
4. 板块轮动中的受益者或受损者
5. 技术面出现重要信号的股票

请涵盖不同板块和市值，例如：
- 蓝筹股（如四大银行、BHP、RIO等）
- 科技股（如XRO、WTC等）
- 资源股（如锂矿、稀土、铀矿等）
- 医疗/消费/零售等其他板块

对每只选中的股票，请提供：
- **股票代码与公司名称**
- **本周股价表现**（涨幅、跌幅、成交量等）
- **本周驱动因素**（公司动态、行业新闻、宏观环境等）
- **券商观点汇总**（评级、目标价、最新研究报告摘要）
- **技术分析摘要**（趋势、支撑位、阻力位、技术指标等）
- **投资建议**（买入/持有/卖出及具体理由）

请用中文回复，要有数据支撑。如果实时数据中没有足够的股票信息，请说明并基于你的知识库进行分析。"""

    stock_analysis = call_zai_api(stock_analysis_prompt, realtime_context)

    # 第五部分：投资日历
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在整理下周投资日历...")
    investment_calendar_prompt = """你是澳洲股市投资日历专家。请提供下周（下周一到下周五）ASX的重要事件，包括：

1. 重要财报发布日期
2. 经济数据公布
3. 央行决议/讲话
4. IPO日历
5. 除息除权日

请用中文回复，按日期排序。如果无法获取确切日期，请说明"待公布"并提供一般性指引。"""

    investment_calendar = call_zai_api(investment_calendar_prompt, realtime_context)

    # 第六部分：风险提示
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在分析风险因素...")
    risk_alert_prompt = """你是澳洲股市风险分析专家。请分析当前投资者需要注意的主要风险，包括：

1. 宏观经济风险（利率、通胀、汇率）
2. 地缘政治风险
3. 板块特定风险
4. 市场估值风险
5. 流动性风险

请用中文回复，每项风险给出具体说明和应对建议。"""

    risk_alert = call_zai_api(risk_alert_prompt, realtime_context)

    return {
        "market_overview": market_overview,
        "broker_recommendations": broker_recommendations,
        "sector_analysis": sector_analysis,
        "stock_analysis": stock_analysis,
        "investment_calendar": investment_calendar,
        "risk_alert": risk_alert
    }


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

    # 转换Markdown为HTML
    market_overview_html = markdown_to_html(research_data.get('market_overview', '暂无数据'))
    broker_recommendations_html = markdown_to_html(research_data.get('broker_recommendations', '暂无数据'))
    sector_analysis_html = markdown_to_html(research_data.get('sector_analysis', '暂无数据'))
    stock_analysis_html = markdown_to_html(research_data.get('stock_analysis', '暂无数据'))
    investment_calendar_html = markdown_to_html(research_data.get('investment_calendar', '暂无数据'))
    risk_alert_html = markdown_to_html(research_data.get('risk_alert', '暂无数据'))

    html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ASX每日市场报告 - {report_date}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
            line-height: 1.8;
            color: #333;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            border-radius: 12px;
            padding: 40px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            border-bottom: 3px solid #007AFF;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            color: #007AFF;
            margin: 0 0 10px 0;
            font-size: 28px;
        }}
        .header .subtitle {{
            color: #666;
            font-size: 14px;
        }}
        .section {{
            margin-bottom: 35px;
        }}
        .section-title {{
            color: #007AFF;
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 15px;
            padding-bottom: 8px;
            border-bottom: 2px solid #E8F2FF;
        }}
        .content {{
            background-color: #F8F9FA;
            padding: 20px;
            border-radius: 8px;
            font-size: 14px;
            line-height: 1.8;
        }}
        /* Markdown转HTML样式 */
        .content h1 {{
            color: #007AFF;
            font-size: 22px;
            margin-top: 20px;
            margin-bottom: 10px;
            border-bottom: 2px solid #E8F2FF;
            padding-bottom: 5px;
        }}
        .content h2 {{
            color: #007AFF;
            font-size: 20px;
            margin-top: 18px;
            margin-bottom: 8px;
        }}
        .content h3 {{
            color: #333;
            font-size: 18px;
            margin-top: 15px;
            margin-bottom: 6px;
        }}
        .content p {{
            margin: 10px 0;
        }}
        .content ul, .content ol {{
            margin: 10px 0;
            padding-left: 25px;
        }}
        .content li {{
            margin: 5px 0;
        }}
        .content strong {{
            color: #007AFF;
            font-weight: 600;
        }}
        .content code {{
            background-color: #e8e8e8;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 13px;
        }}
        .content pre {{
            background-color: #2d2d2d;
            color: #f8f8f2;
            padding: 15px;
            border-radius: 8px;
            overflow-x: auto;
            margin: 15px 0;
        }}
        .content pre code {{
            background-color: transparent;
            padding: 0;
            color: inherit;
        }}
        .content table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        .content table th {{
            background-color: #007AFF;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}
        .content table td {{
            padding: 10px 12px;
            border-bottom: 1px solid #ddd;
        }}
        .content table tr:hover {{
            background-color: #f0f8ff;
        }}
        .content hr {{
            border: none;
            border-top: 2px solid #E8F2FF;
            margin: 20px 0;
        }}
        .highlight {{
            background-color: #FFF3CD;
            padding: 2px 6px;
            border-radius: 4px;
        }}
        .risk {{
            background-color: #FDE8E8;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            text-align: center;
            color: #888;
            font-size: 12px;
        }}
        .stock-tag {{
            display: inline-block;
            background-color: #007AFF;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            margin-right: 5px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #007AFF;
            color: white;
            font-weight: 600;
        }}
        tr:hover {{
            background-color: #F8F9FA;
        }}
        .positive {{ color: #28a745; font-weight: 600; }}
        .negative {{ color: #dc3545; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🇦🇺 ASX每日市场报告</h1>
            <div class="subtitle">{report_date} | 澳大利亚东部标准时间 08:00 | 自动生成报告</div>
        </div>

        <div class="section">
            <div class="section-title">📊 市场概况</div>
            <div class="content">{market_overview_html}</div>
        </div>

        <div class="section">
            <div class="section-title">📈 券商最新推荐</div>
            <div class="content">{broker_recommendations_html}</div>
        </div>

        <div class="section">
            <div class="section-title">🏭 热门板块分析</div>
            <div class="content">{sector_analysis_html}</div>
        </div>

        <div class="section">
            <div class="section-title">🎯 个股深度分析</div>
            <div class="content">{stock_analysis_html}</div>
        </div>

        <div class="section">
            <div class="section-title">📅 近期投资日历</div>
            <div class="content">{investment_calendar_html}</div>
        </div>

        <div class="section">
            <div class="section-title">⚠️ 风险提示</div>
            <div class="content risk">{risk_alert_html}</div>
        </div>

        <div class="footer">
            <p>本报告由AI自动生成，仅供参考，不构成投资建议。</p>
            <p>股市有风险，投资需谨慎。请咨询专业投资顾问做出决策。</p>
            <p>报告生成时间: {now.strftime('%Y-%m-%d %H:%M:%S')}</p>
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
        msg['Subject'] = Header(f"🇦🇺 ASX每日市场报告 - {report_date}", 'utf-8')
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
            <td><a href="{report_file.name}" class="btn-view">查看报告</a></td>
        </tr>
        """

    # 生成完整的index.html
    index_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ASX每日市场报告 - 归档</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            border-radius: 12px;
            padding: 40px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            border-bottom: 3px solid #007AFF;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            color: #007AFF;
            margin: 0 0 10px 0;
            font-size: 32px;
        }}
        .header .subtitle {{
            color: #666;
            font-size: 14px;
        }}
        .info-box {{
            background-color: #E8F2FF;
            border-left: 4px solid #007AFF;
            padding: 15px 20px;
            margin-bottom: 25px;
            border-radius: 4px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th {{
            background-color: #007AFF;
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }}
        td {{
            padding: 12px 15px;
            border-bottom: 1px solid #ddd;
        }}
        tr:hover {{
            background-color: #f8f9fa;
        }}
        .btn-view {{
            display: inline-block;
            background-color: #007AFF;
            color: white;
            padding: 8px 20px;
            text-decoration: none;
            border-radius: 6px;
            transition: background-color 0.3s;
        }}
        .btn-view:hover {{
            background-color: #0051D5;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            text-align: center;
            color: #888;
            font-size: 12px;
        }}
        .stats {{
            display: flex;
            justify-content: space-around;
            margin: 20px 0;
        }}
        .stat-item {{
            text-align: center;
        }}
        .stat-number {{
            font-size: 32px;
            font-weight: bold;
            color: #007AFF;
        }}
        .stat-label {{
            color: #666;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🇦🇺 ASX每日市场报告</h1>
            <div class="subtitle">澳大利亚股市每日投资报告归档</div>
        </div>

        <div class="info-box">
            <strong>📊 关于本报告</strong><br>
            本报告由AI自动生成，每日早上8点（AEST）更新。报告涵盖ASX市场概况、券商推荐、热门板块分析、个股深度分析等内容。
        </div>

        <div class="stats">
            <div class="stat-item">
                <div class="stat-number">{len(report_files)}</div>
                <div class="stat-label">历史报告数</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">每日</div>
                <div class="stat-label">更新频率</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">08:00</div>
                <div class="stat-label">发布时间 (AEST)</div>
            </div>
        </div>

        <h2 style="color: #007AFF; margin-top: 30px;">📁 历史报告归档</h2>
        <table>
            <thead>
                <tr>
                    <th>日期</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
                {report_list_html}
            </tbody>
        </table>

        <div class="footer">
            <p>本报告由AI自动生成，仅供参考，不构成投资建议。</p>
            <p>股市有风险，投资需谨慎。请咨询专业投资顾问做出决策。</p>
            <p>最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} AEST</p>
        </div>
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

    summary = f"""
{'='*60}
ASX每日市场报告
{'='*60}
日期: {now.strftime('%Y年%m月%d日 %H:%M')} AEST
生成方式: AI自动生成

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 市场概况
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{research_data.get('market_overview', '暂无数据')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 券商最新推荐
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{research_data.get('broker_recommendations', '暂无数据')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏭 热门板块分析
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{research_data.get('sector_analysis', '暂无数据')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 个股深度分析
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{research_data.get('stock_analysis', '暂无数据')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 近期投资日历
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{research_data.get('investment_calendar', '暂无数据')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 风险提示
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{research_data.get('risk_alert', '暂无数据')}

{'='*60}
免责声明: 本报告由AI自动生成，仅供参考，不构成投资建议。
股市有风险，投资需谨慎。
{'='*60}
"""
    return summary


def main():
    """主函数"""
    print("="*60)
    print("ASX每日市场报告生成器")
    print("="*60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 检查配置
    if not ZAI_API_KEY:
        print("⚠️ 警告: 未设置ZAI_API_KEY环境变量")
        print("请运行: export ZAI_API_KEY='your_api_key'")
        return

    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("⚠️ 警告: 未设置Gmail配置")
        print("请运行: export GMAIL_ADDRESS='your@gmail.com'")
        print("请运行: export GMAIL_APP_PASSWORD='your_app_password'")
        return

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
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 发送邮件中...")
        email_sent = send_email(report_html, report_date)

        if email_sent:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 周报生成完成！")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 周报已生成但邮件发送失败")

    except Exception as e:
        print(f"❌ 发生错误: {str(e)}")
        import traceback
        traceback.print_exc()

    print()
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)


if __name__ == "__main__":
    main()
