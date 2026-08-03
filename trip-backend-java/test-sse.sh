#!/bin/bash

# SSE 流式测试脚本
# 测试 TripController.recommend-stream 端点

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
USERNAME="${USERNAME:-e4test}"
PASSWORD="${PASSWORD:-EvalTest@2026}"

echo "=========================================="
echo "SSE 流式测试"
echo "=========================================="
echo "Base URL: $BASE_URL"
echo ""

# 1. 获取 token
echo "【1】获取认证 token..."
LOGIN_RESP=$(curl -s -X POST "$BASE_URL/api/user/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" 2>&1)

echo "Login 响应: $LOGIN_RESP"

if echo "$LOGIN_RESP" | grep -q "Too many requests"; then
    echo "⚠️  被限流，等待 120 秒后重试..."
    sleep 120

    echo "重试获取 token..."
    LOGIN_RESP=$(curl -s -X POST "$BASE_URL/api/user/login" \
      -H "Content-Type: application/json" \
      -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" 2>&1)
    echo "Login 响应: $LOGIN_RESP"
fi

TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('data',{}).get('token',''))" 2>/dev/null || echo "")

if [ -z "$TOKEN" ]; then
    echo "❌ 获取 token 失败"
    echo "请检查服务是否正常运行，或稍后重试"
    exit 1
fi

echo "✅ Token 获取成功（长度: ${#TOKEN}）"
echo ""

# 2. 测试 SSE 端点
echo "【2】测试 SSE 流式端点..."
echo "请求: POST /api/trip/recommend-stream"
echo "参数: {\"city\":\"北京\",\"days\":3,\"budget\":5000}"
echo ""
echo "SSE 事件流："
echo "----------------------------------------"

curl -N -X POST "$BASE_URL/api/trip/recommend-stream" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"city":"北京","days":3,"budget":5000}' 2>&1 | while IFS= read -r line; do
    echo "$line"
    # 检测是否结束
    if echo "$line" | grep -q '"type": "end"'; then
        echo "----------------------------------------"
        echo "✅ SSE 流正常结束"
        break
    fi
    # 检测错误
    if echo "$line" | grep -q '"type": "error"'; then
        echo "----------------------------------------"
        echo "❌ SSE 流出错"
        break
    fi
done

echo ""
echo "=========================================="
echo "✅ SSE 测试完成"
echo "=========================================="
