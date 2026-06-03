# ASX每周市场报告自动化系统 | ASX Weekly Market Report Automation System

> 每周六早上8点（AEST）自动生成并发送澳洲股市(ASX)周报到您的邮箱，并发布到GitHub Pages
>
> Automatically generate and send ASX (Australian Securities Exchange) weekly market reports to your email every Saturday at 8 AM (AEST) and publish to GitHub Pages

## 功能特点 | Features

- 📊 **市场概况 | Market Overview**: ASX指数表现、板块涨跌、市场情绪分析 | ASX index performance, sector changes, market sentiment analysis
- 📈 **券商推荐 | Broker Recommendations**: 最新买入评级和目标价 | Latest buy ratings and price targets
- 🏭 **板块分析 | Sector Analysis**: 矿业、科技、银行、医疗等热门板块 | Popular sectors including mining, technology, banking, healthcare
- 🎯 **个股深度 | Stock Insights**: 重点股票详细分析（BHP、XRO等）| Detailed analysis of key stocks (BHP, XRO, etc.)
- 📅 **投资日历 | Investment Calendar**: 近期重要事件提醒 | Important events reminder for upcoming days
- 🌐 **GitHub Pages | Web Archive**: 所有历史报告自动发布到GitHub Pages | All historical reports automatically published to GitHub Pages
- ⚠️ **风险提示 | Risk Analysis**: 投资风险分析 | Investment risk analysis

## 系统要求 | System Requirements

- macOS/Linux (已测试 | Tested)
- Python 3.8 或更高版本 | Python 3.8 or higher
- 稳定的网络连接 | Stable internet connection
- Gmail账号 | Gmail account

## 🔒 安全设计 | Security Design

本系统采用最佳安全实践：| This system follows security best practices:

1. **环境变量隔离 | Environment Variable Isolation**: 所有敏感信息存储在 `.env` 文件中 | All sensitive information is stored in `.env` file
2. **Git保护 | Git Protection**: `.env` 文件已加入 `.gitignore`，不会被提交 | `.env` file is in `.gitignore` and won't be committed
3. **文件权限 | File Permissions**: `.env` 文件权限自动设置为 `600`（仅所有者可读写）| `.env` permissions are automatically set to `600` (owner read/write only)
4. **GitHub Secrets | GitHub Secrets**: 支持GitHub Actions，使用Secrets存储敏感信息 | Supports GitHub Actions using Secrets for sensitive data

## 快速开始 | Quick Start

### 方式一：本地运行 | Method 1: Local Execution

#### 1. 安装配置 | 1. Installation and Setup

```bash
cd ~/Downloads/asx_weekly_report
chmod +x setup.sh
./setup.sh
```

安装脚本会引导您完成：| The installation script will guide you through:
- Python环境检查 | Python environment check
- 依赖包安装 | Dependency installation
- 环境变量配置（保存到 .env）| Environment variable configuration (saved to .env)
- 定时任务设置 | Scheduled task setup

#### 2. 所需配置 | 2. Required Configuration

**Z.ai GLM API Key**
- 访问 https://open.bigmodel.cn/ | Visit https://open.bigmodel.cn/
- 注册并获取API Key | Register and obtain API Key
- 选择 `glm-4-flash` 模型（经济快速）| Select `glm-4-flash` model (economical and fast)

**Gmail 应用密码 | Gmail App Password**
1. 访问 https://myaccount.google.com/security | Visit https://myaccount.google.com/security
2. 启用两步验证 | Enable two-factor authentication
3. 在"两步验证"下方找到"应用密码" | Find "App passwords" under two-factor authentication
4. 创建一个新的应用密码（16位）| Create a new app password (16 characters)

#### 3. 手动运行 | 3. Manual Execution

```bash
cd ~/Downloads/asx_weekly_report
./run_report.sh
```

---

### 方式二：GitHub Actions 运行 | Method 2: GitHub Actions Execution

#### 1. 推送到GitHub | 1. Push to GitHub

```bash
cd ~/Downloads/asx_weekly_report
git init
git add .
git commit -m "Initial commit: ASX weekly report system"

# 创建GitHub仓库后 | After creating a GitHub repository
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

#### 2. 配置GitHub Secrets | 2. Configure GitHub Secrets

在GitHub仓库中添加以下Secrets：| Add the following Secrets in your GitHub repository:

1. 进入仓库 Settings → Secrets and variables → Actions | Go to Repository Settings → Secrets and variables → Actions
2. 点击 "New repository secret" | Click "New repository secret"
3. 添加以下Secrets：| Add the following Secrets:

| Secret名称 | Secret Name | 说明 | Description | 示例 | Example |
|-----------|------|------|------|------|---|
| `ZAI_API_KEY` | `ZAI_API_KEY` | Z.ai GLM API密钥 | Z.ai GLM API key | `your_api_key_here` | `your_api_key_here` |
| `GMAIL_ADDRESS` | `GMAIL_ADDRESS` | Gmail邮箱地址 | Gmail email address | `your@gmail.com` | `your@gmail.com` |
| `GMAIL_APP_PASSWORD` | `GMAIL_APP_PASSWORD` | Gmail应用密码（16位）| Gmail app password (16 characters) | `abcd efgh ijkl mnop` | `abcd efgh ijkl mnop` |
| `RECIPIENT_EMAIL` | `RECIPIENT_EMAIL` | 收件人邮箱（可选）| Recipient email (optional) | `recipient@example.com` | `recipient@example.com` |

#### 3. 启用GitHub Pages | 3. Enable GitHub Pages

- 进入仓库的 Settings → Pages | Go to Repository Settings → Pages
- Source 选择 "Deploy from a branch" | Select "Deploy from a branch" as Source
- Branch 选择 "main" 和 "/docs" | Select "main" branch and "/docs" folder
- 点击 Save | Click Save

#### 4. 启用Workflow | 4. Enable Workflow

- 进入仓库的 "Actions" 标签 | Go to the "Actions" tab in your repository
- 找到 "ASX Weekly Investment Report" workflow | Find the "ASX Weekly Investment Report" workflow
- 点击 "Enable workflow" | Click "Enable workflow"

#### 5. 手动测试 | 5. Manual Testing

- 在Actions页面，选择 "ASX Weekly Investment Report" | On the Actions page, select "ASX Weekly Investment Report"
- 点击 "Run workflow" 按钮手动触发 | Click the "Run workflow" button to trigger manually
- 等待运行完成后，访问 `https://YOUR_USERNAME.github.io/YOUR_REPO/` 查看报告 | After completion, visit `https://YOUR_USERNAME.github.io/YOUR_REPO/` to view the report

## 文件结构 | File Structure

```
~/Downloads/asx_weekly_report/
├── asx_weekly_reporter.py         # 主程序 | Main program
├── setup.sh                        # 安装脚本 | Setup script
├── run_report.sh                   # 快速启动脚本 | Quick start script
├── .env.example                    # 环境变量示例 | Environment variables example
├── .gitignore                      # Git忽略文件（包含.env）| Git ignore file (includes .env)
├── .github/
│   └── workflows/
│       └── asx-weekly-report.yml  # GitHub Actions配置 | GitHub Actions configuration
├── README.md                       # 说明文档 | Documentation
├── docs/                           # GitHub Pages输出目录 | GitHub Pages output directory
│   ├── index.html                  # 报告归档首页 | Report archive index
│   └── asx_report_YYYYMMDD.html   # 每周报告HTML | Weekly report HTML
└── logs/                           # 运行日志 | Run logs
    └── cron.log
```

## 环境变量 | Environment Variables

复制 `.env.example` 为 `.env` 并填入真实配置：| Copy `.env.example` to `.env` and fill in real configuration:

```bash
cp .env.example .env
nano .env  # 或使用您喜欢的编辑器 | or use your preferred editor
```

```bash
# Z.ai GLM API配置 | Z.ai GLM API Configuration
ZAI_API_KEY=your_api_key_here

# Gmail SMTP配置 | Gmail SMTP Configuration
GMAIL_ADDRESS=your@gmail.com
GMAIL_APP_PASSWORD=your_app_password

# 收件人邮箱（留空则发送给自己）| Recipient email (leave blank to send to yourself)
RECIPIENT_EMAIL=
```

## 报告输出 | Report Output

### HTML版本 | HTML Version
精美的HTML格式报告，直接在浏览器中查看 | Beautiful HTML formatted report that can be viewed directly in a browser

### 纯文本版本 | Plain Text Version
包含完整内容的纯文本格式 | Complete content in plain text format

### 输出位置 | Output Location

**本地 | Local:**
```
~/Downloads/asx_weekly_report/
├── asx_report_20260221.html
└── asx_report_20260221.txt
```

**GitHub Pages:**
```
https://YOUR_USERNAME.github.io/YOUR_REPO/
├── index.html                     # 报告归档首页 | Report archive index
└── asx_report_20260221.html       # 每周报告 | Weekly report
```

## 定时任务 | Scheduled Tasks

### 本地Cron | Local Cron

```bash
# 查看当前定时任务 | View current scheduled tasks
crontab -l

# 编辑定时任务 | Edit scheduled tasks
crontab -e
```

默认配置：每周六早上8:00运行 | Default: Run every Saturday at 8:00 AM

### GitHub Actions

默认配置：每周五UTC 22:00（澳大利亚东部标准时间周六早上8:00）| Default: Every Friday at 22:00 UTC (Saturday 8:00 AM AEST)

可在 `.github/workflows/asx-weekly-report.yml` 中修改时间。| Modify the time in `.github/workflows/asx-weekly-report.yml`

## 故障排除 | Troubleshooting

### 邮件发送失败 | Email Sending Failed
- 检查Gmail应用密码是否正确 | Check if Gmail app password is correct
- 确认已开启两步验证 | Confirm two-factor authentication is enabled
- 查看日志 `logs/cron.log` | Check logs in `logs/cron.log`

### API调用失败 | API Call Failed
- 检查ZAI_API_KEY是否正确 | Check if ZAI_API_KEY is correct
- 确认网络连接正常 | Confirm network connection is working
- 检查API余额 | Check API balance

### 定时任务未运行 | Scheduled Task Not Running
- 检查cron服务状态：`sudo launchctl list` (macOS) | Check cron service status: `sudo launchctl list` (macOS)
- 查看系统日志 | Check system logs
- 确认脚本路径正确 | Confirm script path is correct

### GitHub Actions失败 | GitHub Actions Failed
- 检查Secrets是否正确配置 | Check if Secrets are configured correctly
- 查看Actions运行日志 | View Actions run logs
- 确认workflow已启用 | Confirm workflow is enabled

## 修改配置 | Modify Configuration

### 修改发送时间 | Change Send Time

**本地Cron | Local Cron:**
```bash
crontab -e
# 将 "0 8 * * 6" 改为您想要的时间 | Change "0 8 * * 6" to your desired time
# 格式: 分 时 日 月 周 | Format: minute hour day month weekday
```

**GitHub Actions:**
修改 `.github/workflows/asx-weekly-report.yml` 中的 cron 表达式 | Modify the cron expression in `.github/workflows/asx-weekly-report.yml`

### 修改报告内容 | Change Report Content
编辑 `asx_weekly_reporter.py` 中的prompt部分 | Edit the prompt section in `asx_weekly_reporter.py`

### 添加新的分析板块 | Add New Analysis Sections
在 `generate_market_research()` 函数中添加新的API调用 | Add new API calls in the `generate_market_research()` function

## 卸载 | Uninstall

```bash
# 删除定时任务 | Delete scheduled task
crontab -e
# 删除包含 asx_weekly_reporter.py 的行 | Delete the line containing asx_weekly_reporter.py

# 删除文件 | Delete files
cd ~
rm -rf Downloads/asx_weekly_report
```

## 常见问题 | FAQ

**Q: 可以改成每天发送吗？| Can I change it to send daily?**
A: 可以，修改crontab表达式为 `0 8 * * *` | Yes, change the crontab expression to `0 8 * * *`

**Q: 可以添加多个收件人吗？| Can I add multiple recipients?**
A: 可以，在代码中修改邮件发送部分支持多收件人 | Yes, modify the email sending section in the code to support multiple recipients

**Q: API调用有费用吗？| Is there a cost for API calls?**
A: Z.ai GLM的 `glm-4-flash` 模型价格较低，适合频繁调用 | The `glm-4-flash` model from Z.ai GLM is low-cost and suitable for frequent calls

**Q: 报告可以自定义吗？| Can I customize the report?**
A: 可以，编辑 `asx_weekly_reporter.py` 中的prompt和HTML模板 | Yes, edit the prompt and HTML template in `asx_weekly_reporter.py`

**Q: 推送到GitHub安全吗？| Is it safe to push to GitHub?**
A: 安全。`.env` 文件在 `.gitignore` 中，不会被提交。GitHub版本使用Secrets存储敏感信息。| Safe. The `.env` file is in `.gitignore` and won't be committed. The GitHub version uses Secrets for sensitive information.

**Q: 如何查看GitHub Actions的运行日志？| How to check GitHub Actions run logs?**
A: 进入仓库的Actions标签，选择具体的运行记录查看详细日志。| Go to the Actions tab in your repository and select a specific run to view detailed logs.

## 免责声明 | Disclaimer

本报告由AI自动生成，内容仅供参考，不构成投资建议。股市有风险，投资需谨慎。| This report is automatically generated by AI and is for reference only, not investment advice. Stock markets involve risk; please invest cautiously.

## 许可 | License

MIT License

---

**问题反馈 | Feedback**: 如有问题请检查 `logs/cron.log` 日志文件或GitHub Actions运行日志 | If you have any issues, please check the `logs/cron.log` file or GitHub Actions run logs
