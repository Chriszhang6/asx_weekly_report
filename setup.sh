#!/bin/bash
###############################################################################
# 澳洲股市周报自动化系统 - 安装配置脚本
#
# 安全说明：
# - 本脚本不会存储任何敏感信息
# - 所有敏感信息将保存在 .env 文件中（已在 .gitignore 中）
# - .env 文件权限设置为 600（仅所有者可读写）
###############################################################################

set -e  # 遇到错误立即退出

echo "=========================================="
echo "澳洲股市投资周报 - 自动化系统安装"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ============== 步骤1: 检查Python环境 ==============
echo -e "${YELLOW}[步骤1/6]${NC} 检查Python环境..."

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到python3${NC}"
    echo "请先安装Python 3.8或更高版本"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}✓${NC} 找到Python版本: $PYTHON_VERSION"

# ============== 步骤2: 安装依赖 ==============
echo ""
echo -e "${YELLOW}[步骤2/6]${NC} 安装Python依赖包..."

# 检查是否有pip
if ! command -v pip3 &> /dev/null; then
    echo "未找到pip3，尝试安装..."
    python3 -m ensurepip --upgrade 2>/dev/null || true
fi

echo "正在安装依赖: requests, yfinance, html2text"
pip3 install --user requests yfinance html2text 2>/dev/null || pip3 install requests yfinance html2text

echo -e "${GREEN}✓${NC} 依赖安装完成"

# ============== 步骤3: 创建 .env 文件 ==============
echo ""
echo -e "${YELLOW}[步骤3/6]${NC} 配置环境变量..."
echo ""

ENV_FILE="$SCRIPT_DIR/.env"

if [ -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}发现已存在的 .env 文件${NC}"
    read -p "是否要重新配置？(y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "跳过环境变量配置，使用现有配置"
    else
        echo "备份旧配置..."
        mv "$ENV_FILE" "$ENV_FILE.backup"
        echo ""
    fi
fi

if [ ! -f "$ENV_FILE" ]; then
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  环境变量配置向导${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "所有配置将保存到 .env 文件（不会被提交到Git）"
    echo ""

    # Z.ai API Key
    echo -e "${YELLOW}[1/4] Z.ai GLM API Key${NC}"
    echo "获取地址: https://open.bigmodel.cn/"
    read -p "请输入您的API Key: " ZAI_API_KEY
    echo ""

    # Gmail配置
    echo -e "${YELLOW}[2/4] Gmail 配置${NC}"
    read -p "请输入您的Gmail邮箱地址: " GMAIL_ADDRESS
    echo ""
    echo "Gmail应用密码获取方式："
    echo "  1. 访问 https://myaccount.google.com/security"
    echo "  2. 启用两步验证"
    echo "  3. 在'两步验证'下方找到'应用密码'"
    echo "  4. 创建一个新的应用密码"
    echo ""
    read -sp "请输入您的Gmail应用密码（16位）: " GMAIL_APP_PASSWORD
    echo ""
    echo ""

    # 收件人邮箱
    echo -e "${YELLOW}[3/4] 收件人邮箱${NC}"
    read -p "请输入收件人邮箱（直接回车使用发送邮箱）: " RECIPIENT_EMAIL
    if [ -z "$RECIPIENT_EMAIL" ]; then
        RECIPIENT_EMAIL="$GMAIL_ADDRESS"
    fi
    echo ""

    # 确认信息
    echo -e "${YELLOW}[4/4] 确认配置${NC}"
    echo ""
    echo "发送邮箱: $GMAIL_ADDRESS"
    echo "收件邮箱: $RECIPIENT_EMAIL"
    echo "Z.ai API Key: ${ZAI_API_KEY:0:8}...（已隐藏）"
    echo ""
    read -p "确认以上配置正确？(Y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        echo "配置已取消"
        exit 1
    fi

    # 写入.env文件
    cat > "$ENV_FILE" << EOF
# Z.ai GLM API配置
ZAI_API_KEY=$ZAI_API_KEY

# Gmail SMTP配置
GMAIL_ADDRESS=$GMAIL_ADDRESS
GMAIL_APP_PASSWORD=$GMAIL_APP_PASSWORD

# 收件人邮箱
RECIPIENT_EMAIL=$RECIPIENT_EMAIL
EOF

    # 设置文件权限为只有所有者可读写
    chmod 600 "$ENV_FILE"
    echo ""
    echo -e "${GREEN}✓${NC} 环境变量已保存到: $ENV_FILE"
    echo -e "${GREEN}✓${NC} 文件权限已设置为 600（仅所有者可读写）"
fi

# ============== 步骤4: 创建启动脚本 ==============
echo ""
echo -e "${YELLOW}[步骤4/6]${NC} 创建启动脚本..."

cat > "$SCRIPT_DIR/run_report.sh" << 'EOF'
#!/bin/bash
# 澳洲股市周报启动脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 加载环境变量
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | grep -v '^$' | xargs)
fi

# 运行报告脚本
python3 asx_weekly_reporter.py
EOF

chmod +x "$SCRIPT_DIR/run_report.sh"
echo -e "${GREEN}✓${NC} 启动脚本已创建: run_report.sh"

# ============== 步骤5: 可选 - 设置定时任务 ==============
echo ""
echo -e "${YELLOW}[步骤5/6]${NC} 设置定时任务（可选）..."
echo ""
read -p "是否设置每周六早上8:00自动运行？(Y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "跳过定时任务设置"
    SKIP_CRON=1
fi

if [ -z "$SKIP_CRON" ]; then
    # 读取当前crontab
    CURRENT_CRON=$(crontab -l 2>/dev/null || true)

    # 检查是否已经存在相同的任务
    if echo "$CURRENT_CRON" | grep -q "asx_weekly_reporter.py"; then
        echo -e "${YELLOW}检测到已存在的周报定时任务${NC}"
        read -p "是否要重新设置？(y/N) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            SKIP_CRON=1
        fi
    fi

    if [ -z "$SKIP_CRON" ]; then
        # 删除旧的任务
        NEW_CRON=$(echo "$CURRENT_CRON" | grep -v "asx_weekly_reporter.py" || true)
        echo "$NEW_CRON" | crontab -

        # 创建日志目录
        mkdir -p "$SCRIPT_DIR/logs"

        # 添加新的cron任务（每周六早上8:00）
        (crontab -l 2>/dev/null; echo "0 8 * * 6 cd $SCRIPT_DIR && . .env && ./run_report.sh >> logs/cron.log 2>&1") | crontab -

        echo -e "${GREEN}✓${NC} 定时任务已设置: 每周六早上8:00"
        echo "  日志文件: $SCRIPT_DIR/logs/cron.log"
    fi
fi

# ============== 步骤6: 测试运行 ==============
echo ""
echo -e "${YELLOW}[步骤6/6]${NC} 测试运行..."
echo ""
read -p "是否现在测试运行一次？(Y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo "正在运行测试..."
    echo ""

    # 加载环境变量并运行
    export $(cat "$ENV_FILE" | grep -v '^#' | grep -v '^$' | xargs)
    python3 asx_weekly_reporter.py

    echo ""
    echo -e "${GREEN}✓${NC} 测试完成！"
    echo ""
    echo "请检查："
    echo "  1. 邮箱是否收到报告"
    echo "  2. ~/Downloads/asx_weekly_report/ 目录是否生成文件"
else
    echo "跳过测试。您可以手动运行: ./run_report.sh"
fi

# ============== 完成 ==============
echo ""
echo "=========================================="
echo -e "${GREEN}安装完成！${NC}"
echo "=========================================="
echo ""

# 安全提示
echo -e "${YELLOW}🔒 安全提醒${NC}"
echo ""
echo "1. .env 文件包含敏感信息，已在 .gitignore 中"
echo "2. 请勿将 .env 文件提交到 Git 或分享给他人"
echo "3. 文件权限已设置为 600（仅所有者可读写）"
echo ""

echo "常用命令："
echo "  • 手动运行周报:    ./run_report.sh"
echo "  • 查看定时任务:    crontab -l"
echo "  • 查看日志:        cat logs/cron.log"
echo "  • 修改配置:        编辑 .env 文件"
echo "  • 查看环境变量:    cat .env"
echo ""

echo "报告保存位置:"
echo "  • HTML版本:        ~/Downloads/asx_weekly_report/*.html"
echo "  • 纯文本版本:      ~/Downloads/asx_weekly_report/*.txt"
echo ""

if [ -z "$SKIP_CRON" ]; then
    echo "下次自动运行: 下周六早上8:00"
fi

echo ""
echo "如需推送到GitHub，请确保："
echo "  1. .env 文件不会被提交（已在 .gitignore 中）"
echo "  2. 如使用GitHub Actions，请在仓库设置中添加 Secrets"
echo ""
