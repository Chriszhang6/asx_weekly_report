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

    reasons = []

    for name, url in news_sources:
        try:
            content = fetch_url(url)
            if content and not content.startswith("获取网页失败"):
                lines = content.split('\n')
                for line in lines:
                    line = line.strip()
                    # 跳过导航
                    if any(skip in line for skip in ['MENU', 'Skip to', 'Login', 'Subscribe']):
                        continue
                    # 检查是否包含市场相关关键词
                    if 20 < len(line) < 200:
                        line_lower = line.lower()
                        if any(keyword.lower() in line_lower for keyword in keywords):
                            if line not in reasons:
                                reasons.append(line)
                                if len(reasons) >= 3:
                                    break
                if len(reasons) >= 3:
                    break
        except Exception as e:
            print(f"        ⚠️  {name} 获取失败: {e}")

    if reasons:
        return "\n".join(f"- {r}" for r in reasons[:3])
    return "暂无明确的市场变动原因"


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
    market_overview_prompt = """你是一名给朋友写邮件的澳洲股市分析师。用简洁直白的语言总结今日ASX市场。

**严格要求：**
- 不要自我介绍，不要写"报告日期"、"分析师"等元信息
- 不要写"根据现有信息无法确认"之类的废话，没有数据就跳过
- 不要加"总结"段落，全文本身就是总结
- 用数字说话，少用形容词
- 全文控制在300字以内

**内容（每项1-2句话）：**
1. ASX 200今日收盘点位、涨跌幅
2. 今日最大的1-2个市场驱动因素
3. 值得注意的板块或个股异动

今天是{current_date}。"""

    market_overview = call_zai_api(market_overview_prompt, realtime_context)

    # 第二部分：个股深度分析
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在进行个股深度分析...")
    stock_analysis_prompt = """根据今日市场新闻，挑选2-3只最值得关注的ASX股票，简要分析。

**严格要求：**
- 不要自我介绍或写报告元信息
- 不要写"根据现有信息无法确认"，没数据就不提
- 每只股票控制在100字以内
- 不要写技术分析（支撑位、阻力位），普通读者不关心
- 只写读者能行动的信息

**每只股票格式：**
- **股票代码 公司名** — 一句话说明今天为什么值得关注
- 股价表现（涨跌幅）
- 关键原因（1-2句话）

请用中文回复，像写给朋友的消息一样直接。"""

    stock_analysis = call_zai_api(stock_analysis_prompt, realtime_context)

    # 第三部分：投资日历
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在整理下周投资日历...")
    investment_calendar_prompt = """列出未来1-2周ASX相关的重要事件。

**格式要求：**
- 每个事件一行：**日期** - 事件（一句话说明影响）
- 只列确定的事件，不确定就不写
- 最多列8个事件
- 不要写开头的引言段落，直接列事件

示例：
- **3月10日** - RBA利率决议，市场预期维持不变
- **3月12日** - NAB商业信心指数公布

请用中文回复。"""

    investment_calendar = call_zai_api(investment_calendar_prompt, realtime_context)

    # 第四部分：风险提示
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在分析风险因素...")
    risk_alert_prompt = """列出当前1-2个最紧迫的市场风险。

**要求：**
- 只写有具体时间点或触发条件的风险
- 不写"地缘政治不确定性"之类的泛泛之谈
- 每个风险2-3句话，说清楚是什么、什么时候、可能怎样
- 如果没有明确的即时风险，就写"当前无特殊风险事件"
- 不要写开头引言

请用中文回复。"""

    risk_alert = call_zai_api(risk_alert_prompt, realtime_context)

    return {
        "market_overview": market_overview,
        "stock_analysis": stock_analysis,
        "investment_calendar": investment_calendar,
        "risk_alert": risk_alert
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
            AI自动生成，仅供参考，不构成投资建议。<br>
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
        AI自动生成，仅供参考。<br>
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
AI自动生成，仅供参考，不构成投资建议。
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
