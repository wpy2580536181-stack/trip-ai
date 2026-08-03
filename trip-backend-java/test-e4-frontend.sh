#!/usr/bin/env bash
# E4 前端集成测试脚本

set -e

echo "=========================================="
echo "E4 前端集成测试"
echo "=========================================="
echo ""

# 配置
FRONTEND_URL="http://localhost:5173"
BACKEND_URL="http://localhost:8000"
TEST_USER="e4test"
TEST_PASSWORD="EvalTest@2026"

# 颜色输出
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 测试计数
passed=0
failed=0

# 测试函数
test_endpoint() {
    local name=$1
    local url=$2
    local expected_status=$3

    echo -n "Testing: $name ... "
    status=$(curl -s -o /dev/null -w "%{http_code}" "$url")

    if [ "$status" -eq "$expected_status" ]; then
        echo -e "${GREEN}PASS${NC} (HTTP $status)"
        ((passed++))
    else
        echo -e "${RED}FAIL${NC} (Expected $expected_status, got $status)"
        ((failed++))
    fi
}

# 1. 检查 Java 后端健康状态
echo "📋 阶段 1：Java 后端验证"
test_endpoint "Java Backend Health" "$BACKEND_URL/health" 200
test_endpoint "Java Backend Health Detail" "$BACKEND_URL/health/detail" 200

# 2. 检查前端服务器
echo ""
echo "📋 阶段 2：前端服务器验证"
test_endpoint "Frontend Server" "$FRONTEND_URL" 200

# 3. 测试 API 代理（前端通过 VITE_API_BASE 调用后端）
echo ""
echo "📋 阶段 3：API 代理验证"

# 获取 token
LOGIN_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/user/login" \
    -H "Content-Type: application/json" \
    -d "{\"identifier\":\"$TEST_USER\",\"password\":\"$TEST_PASSWORD\"}")

TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"token":"[^"]*' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
    echo -e "${RED}FAIL${NC}: 无法获取 token"
    ((failed++))
else
    echo -e "${GREEN}PASS${NC}: Token 获取成功 (${TOKEN:0:20}...)"

    # 测试用户信息端点
    USER_INFO=$(curl -s "$BACKEND_URL/api/user/info" \
        -H "Authorization: Bearer $TOKEN")
    if echo "$USER_INFO" | grep -q '"username"'; then
        echo -e "${GREEN}PASS${NC}: 用户信息接口"
        ((passed++))
    else
        echo -e "${RED}FAIL${NC}: 用户信息接口"
        ((failed++))
    fi

    # 测试会话列表端点
    CONVERSATIONS=$(curl -s "$BACKEND_URL/api/conversations" \
        -H "Authorization: Bearer $TOKEN")
    if echo "$CONVERSATIONS" | grep -q '"data"'; then
        echo -e "${GREEN}PASS${NC}: 会话列表接口"
        ((passed++))
    else
        echo -e "${RED}FAIL${NC}: 会话列表接口"
        ((failed++))
    fi
fi

# 汇总
echo ""
echo "=========================================="
echo "📊 测试汇总：通过 $passed / 失败 $failed"
echo "=========================================="

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ 所有测试通过！${NC}"
    exit 0
else
    echo -e "${RED}❌ 存在失败的测试${NC}"
    exit 1
fi
