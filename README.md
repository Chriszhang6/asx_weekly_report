# 澳洲股市投资周报自动化系统

> 每周六早上8点自动生成并发送澳洲股市(ASX)投资周报到您的邮箱

## 功能特点

- 📊 **市场概况**: ASX指数表现、板块涨跌、市场情绪分析
- 📈 **券商推荐**: 最新买入评级和目标价
- 🏭 **板块分析**: 矿业、科技、银行、医疗等热门板块
- 🎯 **个股深度**: 重点股票详细分析（BHP、XRO等）
- 📅 **投资日历**: 下周重要事件提醒
- ⚠️ **风险提示**: 投资风险分析

## 系统要求

- macOS/Linux (已测试)
- Python 3.8 或更高版本
- 稳定的网络连接
- Gmail账号

## 🔒 安全设计

本系统采用最佳安全实践：

1. **环境变量隔离**: 所有敏感信息存储在 `.env` 文件中
2. **Git保护**: `.env` 文件已加入 `.gitignore`，不会被提交
3. **文件权限**: `.env` 文件权限自动设置为 `600`（仅所有者可读写）
4. **GitHub Secrets**: 支持GitHub Actions，使用Secrets存储敏感信息

## 快速开始

### 方式一：本地运行

#### 1. 安装配置

```bash
cd ~/Downloads/asx_weekly_report
chmod +x setup.sh
./setup.sh
```

安装脚本会引导您完成：
- Python环境检查
- 依赖包安装
- 环境变量配置（保存到 .env）
- 定时任务设置

#### 2. 所需配置

**Z.ai GLM API Key**
- 访问 https://open.bigmodel.cn/
- 注册并获取API Key
- 选择 `glm-4-flash` 模型（经济快速）

**Gmail 应用密码**
1. 访问 https://myaccount.google.com/security
2. 启用两步验证
3. 在"两步验证"下方找到"应用密码"
4. 创建一个新的应用密码（16位）

#### 3. 手动运行

```bash
cd ~/Downloads/asx_weekly_report
./run_report.sh
```

---

### 方式二：GitHub Actions 运行

#### 1. 推送到GitHub

```bash
cd ~/Downloads/asx_weekly_report
git init
git add .
git commit -m "Initial commit: ASX weekly report system"

# 创建GitHub仓库后
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

#### 2. 配置GitHub Secrets

在GitHub仓库中添加以下Secrets：

1. 进入仓库 Settings → Secrets and variables → Actions
2. 点击 "New repository secret"
3. 添加以下Secrets：

| Secret名称 | 说明 | 示例 |
|-----------|------|------|
| `ZAI_API_KEY` | Z.ai GLM API密钥 | `your_api_key_here` |
| `GMAIL_ADDRESS` | Gmail邮箱地址 | `your@gmail.com` |
| `GMAIL_APP_PASSWORD` | Gmail应用密码（16位） | `abcd efgh ijkl mnop` |
| `RECIPIENT_EMAIL` | 收件人邮箱（可选） | `recipient@example.com` |

#### 3. 启用Workflow

- 进入仓库的 "Actions" 标签
- 找到 "ASX Weekly Investment Report" workflow
- 点击 "Enable workflow"

#### 4. 手动测试

- 在Actions页面，选择 "ASX Weekly Investment Report"
- 点击 "Run workflow" 按钮手动触发

## 文件结构

```
~/Downloads/asx_weekly_report/
├── asx_weekly_reporter.py         # 主程序
├── setup.sh                        # 安装脚本
├── run_report.sh                   # 快速启动脚本
├── .env.example                    # 环境变量示例
├── .gitignore                      # Git忽略文件（包含.env）
├── .github/
│   └── workflows/
│       └── asx-weekly-report.yml  # GitHub Actions配置
├── README.md                       # 说明文档
└── logs/                           # 运行日志
    └── cron.log
```

## 环境变量

复制 `.env.example` 为 `.env` 并填入真实配置：

```bash
cp .env.example .env
nano .env  # 或使用您喜欢的编辑器
```

```bash
# Z.ai GLM API配置
ZAI_API_KEY=your_api_key_here

# Gmail SMTP配置
GMAIL_ADDRESS=your@gmail.com
GMAIL_APP_PASSWORD=your_app_password

# 收件人邮箱（留空则发送给自己）
RECIPIENT_EMAIL=
```

## 报告输出

### HTML版本
精美的HTML格式报告，直接在浏览器中查看

### 纯文本版本
包含完整内容的纯文本格式

### 输出位置
```
~/Downloads/asx_weekly_report/
├── asx_weekly_report_2026年02月21日.html
└── asx_weekly_report_2026年02月21日.txt
```

## 定时任务

### 本地Cron

```bash
# 查看当前定时任务
crontab -l

# 编辑定时任务
crontab -e
```

默认配置：每周六早上8:00运行

### GitHub Actions

默认配置：每周六早上8:00 UTC（悉尼时间周六下午7:00）

可在 `.github/workflows/asx-weekly-report.yml` 中修改时间。

## 故障排除

### 邮件发送失败
- 检查Gmail应用密码是否正确
- 确认已开启两步验证
- 查看日志 `logs/cron.log`

### API调用失败
- 检查ZAI_API_KEY是否正确
- 确认网络连接正常
- 检查API余额

### 定时任务未运行
- 检查cron服务状态：`sudo launchctl list` (macOS)
- 查看系统日志
- 确认脚本路径正确

### GitHub Actions失败
- 检查Secrets是否正确配置
- 查看Actions运行日志
- 确认workflow已启用

## 修改配置

### 修改发送时间

**本地Cron:**
```bash
crontab -e
# 将 "0 8 * * 6" 改为您想要的时间
# 格式: 分 时 日 月 周
```

**GitHub Actions:**
修改 `.github/workflows/asx-weekly-report.yml` 中的 cron 表达式

### 修改报告内容
编辑 `asx_weekly_reporter.py` 中的prompt部分

### 添加新的分析板块
在 `generate_market_research()` 函数中添加新的API调用

## 卸载

```bash
# 删除定时任务
crontab -e
# 删除包含 asx_weekly_reporter.py 的行

# 删除文件
cd ~
rm -rf Downloads/asx_weekly_report
```

## 常见问题

**Q: 可以改成每天发送吗？**
A: 可以，修改crontab表达式为 `0 8 * * *`

**Q: 可以添加多个收件人吗？**
A: 可以，在代码中修改邮件发送部分支持多收件人

**Q: API调用有费用吗？**
A: Z.ai GLM的 `glm-4-flash` 模型价格较低，适合频繁调用

**Q: 报告可以自定义吗？**
A: 可以，编辑 `asx_weekly_reporter.py` 中的prompt和HTML模板

**Q: 推送到GitHub安全吗？**
A: 安全。`.env` 文件在 `.gitignore` 中，不会被提交。GitHub版本使用Secrets存储敏感信息。

**Q: 如何查看GitHub Actions的运行日志？**
A: 进入仓库的Actions标签，选择具体的运行记录查看详细日志。

## 免责声明

本报告由AI自动生成，内容仅供参考，不构成投资建议。股市有风险，投资需谨慎。

## 许可

MIT License

---

**问题反馈**: 如有问题请检查 `logs/cron.log` 日志文件或GitHub Actions运行日志
