#!/bin/bash
# 本地开发启动脚本：启动 mainagent 8100 服务（使用 mock 数据）

set -e

# 确保在 mainagent 目录
cd "$(dirname "$0")"

echo "=========================================="
echo "🚀 启动 HLSC MainAgent 本地开发环境"
echo "=========================================="
echo ""

# 检查环境
if ! command -v uv &> /dev/null; then
    echo "❌ 错误: 未找到 uv，请先安装 uv (https://github.com/astral-sh/uv)"
    exit 1
fi

# 显示配置信息
echo "📋 配置信息："
echo "  - AGENT_NAME: $(grep '^AGENT_NAME=' .env.local | cut -d'=' -f2)"
echo "  - SERVER_PORT: $(grep '^SERVER_PORT=' .env.local | cut -d'=' -f2)"
echo "  - MOCK_SEARCH_COUPON: $(grep '^MOCK_SEARCH_COUPON=' .env.local | cut -d'=' -f2)"
echo "  - MOCK_APPLY_COUPON: $(grep '^MOCK_APPLY_COUPON=' .env.local | cut -d'=' -f2)"
echo ""

# 提示选项
echo "💡 选项："
echo "  - 启动 mock 数据服务器（可选）: uv run python mock_data_server.py"
echo "  - 启动时指定端口: ./start_local.sh --port 8100"
echo ""

# 解析参数
PORT=""
for arg in "$@"; do
    if [[ "$PREV_ARG" == "--port" ]]; then
        PORT=$arg
        PREV_ARG=""
        continue
    fi
    PREV_ARG=$arg
done

# 启动服务
echo "🎯 启动 mainagent..."
if [ -z "$PORT" ]; then
    uv run python server.py
else
    echo "  端口: $PORT"
    uv run python server.py --port "$PORT"
fi
