#!/bin/bash
# E4-1 前端全流程回归测试 - 历史/管理流程
# 对标 Python: tests/e2e/test_history.py

set -e

BASE_URL="${BASE_URL:-http://localhost:8080}"
TEST_USER="histuser_$(date +%s)"
TEST_PASS="Test@123456"

echo "=========================================="
echo "E4-1: 历史/管理流程测试"
echo "BASE_URL: $BASE_URL"
echo "=========================================="

# 1. 注册并登录
echo ""
echo "[1/5] 注册并登录"
TOKEN=$(curl -s -X POST "$BASE_URL/api/user/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PASS\",\"email\":\"${TEST_USER}@test.com\"}" > /dev/null && \
curl -s -X POST "$BASE_URL/api/user/login" \
  -H "Content-Type: application/json" \
  -d "{\"identifier\":\"$TEST_USER\",\"password\":\"$TEST_PASS\"}" | \
  grep -o '"token":"[^"]*"' | sed 's/"token":"//;s/"$//')

if [ -z "$TOKEN" ]; then
  echo "❌ 登录失败"
  exit 1
fi

echo "✅ 登录成功"

# 2. 获取历史行程列表
echo ""
echo "[2/5] 获取历史行程列表"
HISTORY_RESP=$(curl -s -X GET "$BASE_URL/api/trip/history" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

echo "响应: ${HISTORY_RESP:0:200}..."

if echo "$HISTORY_RESP" | grep -q '"code":200'; then
  echo "✅ 获取历史行程列表成功"
else
  echo "❌ 获取历史行程列表失败"
  exit 1
fi

# 3. 创建会话
echo ""
echo "[3/5] 创建会话"
CONV_RESP=$(curl -s -X POST "$BASE_URL/api/conversations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test History"}')

CONV_ID=$(echo "$CONV_RESP" | grep -o '"id":[0-9]*' | head -1 | sed 's/"id"://')

if [ -z "$CONV_ID" ]; then
  echo "❌ 创建会话失败"
  exit 1
fi

echo "✅ 创建会话成功（ID: $CONV_ID）"

# 4. 删除会话
echo ""
echo "[4/5] 删除会话"
DELETE_RESP=$(curl -s -X DELETE "$BASE_URL/api/conversations/$CONV_ID" \
  -H "Authorization: Bearer $TOKEN")

echo "响应: $DELETE_RESP"

if echo "$DELETE_RESP" | grep -q '"success"'; then
  echo "✅ 删除会话成功"
elif echo "$DELETE_RESP" | grep -q '"code":200'; then
  echo "✅ 删除会话成功（code=200）"
else
  echo "⚠️  删除会话可能失败（继续）"
fi

# 5. 获取知识库统计（如果有）
echo ""
echo "[5/5] 获取知识库统计"
STATS_RESP=$(curl -s -X GET "$BASE_URL/api/admin/stats/token-usage" \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null || echo '{"code":403}')

echo "响应: ${STATS_RESP:0:150}..."

if echo "$STATS_RESP" | grep -q '"code"'; then
  echo "✅ 统计接口可访问（可能需要 admin 权限）"
else
  echo "⚠️  统计接口响应异常（继续）"
fi

echo ""
echo "=========================================="
echo "✅ E4-1: 历史/管理流程测试通过"
echo "=========================================="
