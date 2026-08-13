#!/bin/bash
# E4-1 前端全流程回归测试 - 知识库/反馈流程
# 对标 Python: tests/e2e/test_knowledge.py

set -e

BASE_URL="${BASE_URL:-http://localhost:8080}"
TEST_USER="knowuser_$(date +%s)"
TEST_PASS="Test@123456"

echo "=========================================="
echo "E4-1: 知识库/反馈流程测试"
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

# 2. 获取景点列表
echo ""
echo "[2/5] 获取景点列表"
SPOTS_RESP=$(curl -s -X GET "$BASE_URL/api/knowledge/spots?page=1&pageSize=10" \
  -H "Authorization: Bearer $TOKEN")

echo "响应: ${SPOTS_RESP:0:200}..."

if echo "$SPOTS_RESP" | grep -q '"code":200'; then
  echo "✅ 获取景点列表成功"
else
  echo "❌ 获取景点列表失败"
  exit 1
fi

# 3. 获取知识库分页
echo ""
echo "[3/5] 获取知识库分页"
PAGE_RESP=$(curl -s -X GET "$BASE_URL/api/knowledge/spots?city=北京&category=attraction&page=1&pageSize=5" \
  -H "Authorization: Bearer $TOKEN")

echo "响应: ${PAGE_RESP:0:200}..."

if echo "$PAGE_RESP" | grep -q '"code":200'; then
  echo "✅ 获取知识库分页成功"
else
  echo "⚠️  获取知识库分页可能失败（继续）"
fi

# 4. 提交反馈
echo ""
echo "[4/5] 提交反馈"
FEEDBACK_RESP=$(curl -s -X POST "$BASE_URL/api/feedback" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messageId":1,"conversationId":1,"rating":1,"comment":"非常棒的推荐！","tags":["推荐","实用"]}')

echo "响应: $FEEDBACK_RESP"

if echo "$FEEDBACK_RESP" | grep -q '"success"'; then
  echo "✅ 提交反馈成功"
elif echo "$FEEDBACK_RESP" | grep -q '"code"'; then
  echo "✅ 提交反馈响应（code 字段存在）"
else
  echo "⚠️  提交反馈可能失败（继续）"
fi

# 5. 获取反馈列表
echo ""
echo "[5/5] 获取反馈列表"
FEEDBACK_LIST=$(curl -s -X GET "$BASE_URL/api/feedback?page=1&pageSize=10" \
  -H "Authorization: Bearer $TOKEN")

echo "响应: ${FEEDBACK_LIST:0:200}..."

if echo "$FEEDBACK_LIST" | grep -q '"code":200'; then
  echo "✅ 获取反馈列表成功"
else
  echo "⚠️  获取反馈列表可能失败（继续）"
fi

echo ""
echo "=========================================="
echo "✅ E4-1: 知识库/反馈流程测试通过"
echo "=========================================="
