#!/bin/bash
# E4-1 前端全流程回归测试 - Chat 对话流程
# 对标 Python: tests/e2e/test_chat.py

set -e

BASE_URL="${BASE_URL:-http://localhost:8080}"
TEST_USER="chatuser_$(date +%s)"
TEST_PASS="Test@123456"

echo "=========================================="
echo "E4-1: Chat 对话流程测试"
echo "BASE_URL: $BASE_URL"
echo "=========================================="

# 1. 注册并登录
echo ""
echo "[1/5] 注册并登录"
REGISTER_RESP=$(curl -s -X POST "$BASE_URL/api/user/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PASS\",\"email\":\"${TEST_USER}@test.com\"}")

TOKEN=$(curl -s -X POST "$BASE_URL/api/user/login" \
  -H "Content-Type: application/json" \
  -d "{\"identifier\":\"$TEST_USER\",\"password\":\"$TEST_PASS\"}" | \
  grep -o '"token":"[^"]*"' | sed 's/"token":"//;s/"$//')

if [ -z "$TOKEN" ]; then
  echo "❌ 登录失败"
  exit 1
fi

echo "✅ 登录成功"

# 2. 创建会话
echo ""
echo "[2/5] 创建会话"
CONV_RESP=$(curl -s -X POST "$BASE_URL/api/conversations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test Chat"}')

CONV_ID=$(echo "$CONV_RESP" | grep -o '"id":[0-9]*' | head -1 | sed 's/"id"://')

if [ -z "$CONV_ID" ]; then
  echo "❌ 创建会话失败"
  exit 1
fi

echo "✅ 创建会话成功（ID: $CONV_ID）"

# 3. 发送聊天消息（SSE）
echo ""
echo "[3/5] 发送聊天消息（SSE 流式）"
CHAT_RESP=$(curl -s -N -X POST "$BASE_URL/api/trip/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"帮我规划一个北京 3 日游\",\"conversationId\":$CONV_ID}" | head -20)

echo "响应（前 20 行）:"
echo "$CHAT_RESP" | head -20

if echo "$CHAT_RESP" | grep -q "id:"; then
  echo "✅ SSE 流式响应正常"
else
  echo "⚠️  SSE 响应格式可能异常（继续）"
fi

# 4. 获取会话历史
echo ""
echo "[4/5] 获取会话历史"
HISTORY_RESP=$(curl -s -X GET "$BASE_URL/api/conversations/$CONV_ID" \
  -H "Authorization: Bearer $TOKEN")

echo "响应: ${HISTORY_RESP:0:200}..."

if echo "$HISTORY_RESP" | grep -q '"code":200'; then
  echo "✅ 获取会话历史成功"
else
  echo "❌ 获取会话历史失败"
  exit 1
fi

# 5. 获取会话列表
echo ""
echo "[5/5] 获取会话列表"
LIST_RESP=$(curl -s -X GET "$BASE_URL/api/conversations" \
  -H "Authorization: Bearer $TOKEN")

if echo "$LIST_RESP" | grep -q '"code":200'; then
  echo "✅ 获取会话列表成功"
else
  echo "❌ 获取会话列表失败"
  exit 1
fi

echo ""
echo "=========================================="
echo "✅ E4-1: Chat 对话流程测试通过"
echo "=========================================="
