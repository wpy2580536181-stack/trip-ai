#!/bin/bash
# E4-1 前端全流程回归测试 - 注册/登录流程
# 对标 Python: tests/e2e/test_auth.py

set -e

BASE_URL="${BASE_URL:-http://localhost:8080}"
TEST_USER="testuser_$(date +%s)"
TEST_PASS="Test@123456"

echo "=========================================="
echo "E4-1: 注册/登录流程测试"
echo "BASE_URL: $BASE_URL"
echo "=========================================="

# 1. 注册用户
echo ""
echo "[1/4] 注册用户: $TEST_USER"
REGISTER_RESP=$(curl -s -X POST "$BASE_URL/api/user/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$TEST_USER\",\"password\":\"$TEST_PASS\",\"email\":\"${TEST_USER}@test.com\"}")

echo "响应: $REGISTER_RESP"

if echo "$REGISTER_RESP" | grep -q '"success"'; then
  echo "✅ 注册成功"
elif echo "$REGISTER_RESP" | grep -q '"code":201'; then
  echo "✅ 注册成功（code=201）"
else
  echo "❌ 注册失败"
  exit 1
fi

# 2. 登录获取 token
echo ""
echo "[2/4] 用户登录"
LOGIN_RESP=$(curl -s -X POST "$BASE_URL/api/user/login" \
  -H "Content-Type: application/json" \
  -d "{\"identifier\":\"$TEST_USER\",\"password\":\"$TEST_PASS\"}")

echo "响应: $LOGIN_RESP"

TOKEN=$(echo "$LOGIN_RESP" | grep -o '"token":"[^"]*"' | sed 's/"token":"//;s/"$//')

if [ -z "$TOKEN" ]; then
  echo "❌ 登录失败（未获取到 token）"
  exit 1
fi

echo "✅ 登录成功（token 长度: ${#TOKEN}）"

# 3. 获取用户信息
echo ""
echo "[3/4] 获取用户信息"
INFO_RESP=$(curl -s -X GET "$BASE_URL/api/user/info" \
  -H "Authorization: Bearer $TOKEN")

echo "响应: $INFO_RESP"

if echo "$INFO_RESP" | grep -q '"code":200'; then
  echo "✅ 获取用户信息成功"
else
  echo "❌ 获取用户信息失败"
  exit 1
fi

# 4. 修改用户信息（可选）
echo ""
echo "[4/4] 修改用户昵称"
UPDATE_RESP=$(curl -s -X PUT "$BASE_URL/api/user/info" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"nickname":"Test User"}')

echo "响应: $UPDATE_RESP"

if echo "$UPDATE_RESP" | grep -q '"success"'; then
  echo "✅ 修改用户信息成功"
elif echo "$UPDATE_RESP" | grep -q '"code":200'; then
  echo "✅ 修改用户信息成功（code=200）"
else
  echo "⚠️  修改用户信息可能失败（继续）"
fi

echo ""
echo "=========================================="
echo "✅ E4-1: 注册/登录流程测试通过"
echo "=========================================="
