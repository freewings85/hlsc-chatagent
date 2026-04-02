#!/bin/bash
# 等待服务就绪后自动运行 searchcoupons 测试

SERVICE_URL="http://127.0.0.1:8100/health"
MAX_WAIT=300  # 最多等待 5 分钟
INTERVAL=5    # 每 5 秒检查一次

echo "==========================================================="
echo "searchcoupons 场景测试 - 等待服务就绪"
echo "==========================================================="
echo ""
echo "检查服务: $SERVICE_URL"
echo "最大等待时间: ${MAX_WAIT}s"
echo ""

elapsed=0
while [ $elapsed -lt $MAX_WAIT ]; do
    if curl -s "$SERVICE_URL" > /dev/null 2>&1; then
        echo "✓ 服务已就绪！"
        echo ""
        echo "==========================================================="
        echo "开始执行测试..."
        echo "==========================================================="
        echo ""

        cd "$(dirname "$0")/../mainagent"
        timeout 300 uv run python ../tests/test_searchcoupons_e2e.py

        exit $?
    fi

    echo "⏳ 等待服务就绪... ($elapsed/${MAX_WAIT}s)"
    sleep $INTERVAL
    elapsed=$((elapsed + INTERVAL))
done

echo ""
echo "✗ 服务未在规定时间内就绪"
echo "请检查："
echo "  1. 服务是否已启动？"
echo "  2. 服务地址是否正确？"
echo "  3. 防火墙是否允许访问？"
exit 1
