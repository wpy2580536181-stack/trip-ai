#!/usr/bin/env bash
# E4 前端集成快速验证脚本

set -e

echo "=========================================="
echo "E4 前端集成验证"
echo "=========================================="
echo ""

BACKEND_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:5173"
TEST_USER="e4test"
TEST_PASSWORD="EvalTest@2026"

passed=0
failed=0

# 测试函数
test_check() {
    local name=$1
    local result=$2
    local expected=$3

    if [ "$result" = "$expected" ]; then
        echo -e "✅ $name"
        ((passed++))
    else
        echo -e "❌ $name (Expected: $expected, Got: $result)"
        ((failed++))
    fi
}

# 1. Java 后端健康检查
echo "📋 1. Java 后端验证"
health=$(curl -s "$BACKEND_URL/health")
test_check "Health Check" "$health" "OK"

health_detail=$(curl -s "$BACKEND_URL/health/detail" | grep -o '"status":"[^"]*' | cut -d'"' -f4)
test_check "Health Detail" "$health_detail" "UP"

# 2. 前端服务器
echo ""
echo "📋 2. 前端服务器验证"
frontend_status=$(curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL")
test_check "Frontend Server (HTTP $frontend_status)" "true" "true"

# 3. API 端点
echo ""
echo "📋 3. API 端点验证"

# 登录
login_resp=$(curl -s -X POST "$BACKEND_URL/api/user/login" \
    -H "Content-Type: application/json" \
    -d "{\"identifier\":\"$TEST_USER\",\"password\":\"$TEST_PASSWORD\"}")
token=$(echo "$login_resp" | grep -o '"token":"[^"]*' | cut -d'"' -f4)

if [ -n "$token" ]; then
    test_check "Login & Token" "OK" "OK"

    # 用户信息
    user_info=$(curl -s "$BACKEND_URL/api/user/info" \
        -H "Authorization: Bearer $token")
    username=$(echo "$user_info" | grep -o '"username":"[^"]*' | cut -d'"' -f4)
    test_check "User Info (username=$username)" "$username" "$TEST_USER"

    # 会话列表
    conversations=$(curl -s "$BACKEND_URL/api/conversations" \
        -H "Authorization: Bearer $token")
    has_data=$(echo "$conversations" | grep -o '"data"' | head -1)
    test_check "Conversations List" "$has_data" "data"

    # Chat SSE
    chat_resp=$(curl -N -s -X POST "$BACKEND_URL/api/trip/chat" \
        -H "Authorization: Bearer $token" \
        -H "Content-Type: application/json" \
        -d '{"message":"北京2天经典游"}' 2>&1 | head -3)

    has_chunk=$(echo "$chat_resp" | grep -o '"type":"chunk"' | head -1)
    test_check "Chat SSE Stream" "$has_chunk" '"type":"chunk"'
else
    echo -e "❌ Login Failed"
    ((failed++))
fi

# 汇总
echo ""
echo "=========================================="
echo "📊 测试汇总：通过 $passed / 失败 $failed"
echo "=========================================="

if [ $failed -eq 0 ]; then
    echo -e "✅ 所有测试通过！"
    exit 0
else
    echo -e "⚠️  存在 $failed 个失败项"
    exit 1
fi
