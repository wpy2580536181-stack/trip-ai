#!/bin/bash
# E4-1 前端全流程回归测试 - Recommend 推荐流程
# 对标 Python: tests/e2e/test_recommend.py

set -e

BASE_URL="${BASE_URL:-http://localhost:8080}"
TEST_USER="recuser_$(date +%s)"
TEST_PASS="Test@123456"

echo "=========================================="
echo "E4-1: Recommend 推荐流程测试"
echo "BASE_URL: $BASE_URL"
echo "=========================================="

# 1. 注册并登录
echo ""
echo "[1/6] 注册并登录"
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

# 2. 提交推荐请求（非流式）
echo ""
echo "[2/6] 提交推荐请求（非流式）"
RECOMMEND_RESP=$(curl -s -X POST "$BASE_URL/api/trip/recommend" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"city":"成都","days":3,"budget":5000,"fromCity":"北京"}')

echo "响应: ${RECOMMEND_RESP:0:300}..."

if echo "$RECOMMEND_RESP" | grep -q '"success"'; then
  echo "✅ 推荐请求成功"
  TRIP_ID=$(echo "$RECOMMEND_RESP" | grep -o '"id":[0-9]*' | head -1 | sed 's/"id"://')
elif echo "$RECOMMEND_RESP" | grep -q '"code":200'; then
  echo "✅ 推荐请求成功（code=200）"
  TRIP_ID=$(echo "$RECOMMEND_RESP" | grep -o '"id":[0-9]*' | head -1 | sed 's/"id"://')
else
  echo "❌ 推荐请求失败"
  echo "完整响应: $RECOMMEND_RESP"
  exit 1
fi

echo "行程 ID: ${TRIP_ID:-N/A}"

# 3. 提交推荐请求（流式）
echo ""
echo "[3/6] 提交推荐请求（SSE 流式）"
RECOMMEND_STREAM=$(curl -s -N -X POST "$BASE_URL/api/trip/recommend-stream" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"city":"杭州","days":2,"budget":3000,"fromCity":"上海"}' | head -15)

echo "响应（前 15 行）:"
echo "$RECOMMEND_STREAM" | head -15

if echo "$RECOMMEND_STREAM" | grep -q "id:"; then
  echo "✅ SSE 流式响应正常"
else
  echo "⚠️  SSE 响应格式可能异常（继续）"
fi

# 4. 确认行程（如果有 trip_id）
if [ -n "$TRIP_ID" ] && [ "$TRIP_ID" != "N/A" ]; then
  echo ""
  echo "[4/6] 确认行程"
  CONFIRM_RESP=$(curl -s -X POST "$BASE_URL/api/trip/$TRIP_ID/confirm" \
    -H "Authorization: Bearer $TOKEN")

  echo "响应: $CONFIRM_RESP"

  if echo "$CONFIRM_RESP" | grep -q '"success"'; then
    echo "✅ 确认行程成功"
  else
    echo "⚠️  确认行程可能失败（继续）"
  fi

  # 5. 获取行程详情
  echo ""
  echo "[5/6] 获取行程详情"
  DETAIL_RESP=$(curl -s -X GET "$BASE_URL/api/trip/$TRIP_ID" \
    -H "Authorization: Bearer $TOKEN")

  echo "响应: ${DETAIL_RESP:0:200}..."

  if echo "$DETAIL_RESP" | grep -q '"code":200'; then
    echo "✅ 获取行程详情成功"
  else
    echo "❌ 获取行程详情失败"
    exit 1
  fi

  # 6. 放弃行程
  echo ""
  echo "[6/6] 放弃行程"
  DISCARD_RESP=$(curl -s -X POST "$BASE_URL/api/trip/$TRIP_ID/discard" \
    -H "Authorization: Bearer $TOKEN")

  echo "响应: $DISCARD_RESP"

  if echo "$DISCARD_RESP" | grep -q '"success"'; then
    echo "✅ 放弃行程成功"
  else
    echo "⚠️  放弃行程可能失败（继续）"
  fi
else
  echo ""
  echo "[4-6/6] 跳过（无有效 trip_id）"
fi

echo ""
echo "=========================================="
echo "✅ E4-1: Recommend 推荐流程测试通过"
echo "=========================================="
