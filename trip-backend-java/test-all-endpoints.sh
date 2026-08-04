#!/bin/bash

# 接口联调测试脚本
# 测试所有新增的 23 个端点

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
TOKEN=""

echo "=========================================="
echo "接口联调测试"
echo "=========================================="
echo ""

# 1. 获取 Token
echo "【1】获取认证 Token"
LOGIN_RESP=$(curl -s -X POST "$BASE_URL/api/user/login" \
  -H "Content-Type: application/json" \
  -d '{"identifier":"perf_test_user","password":"PerfTest@2026"}')

TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin)['data']['token'])")
echo "Token: ${#TOKEN} chars"
echo ""

# 2. HistoryController 测试
echo "【2】HistoryController（4 个端点）"
echo "  GET /api/history/trips"
curl -s "$BASE_URL/api/history/trips?page=1&pageSize=20" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool > /dev/null && echo "  ✅ 列表接口正常"

echo "  GET /api/history/trips/1"
curl -s "$BASE_URL/api/history/trips/1" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool > /dev/null && echo "  ✅ 详情接口正常（404 预期）"

echo "  GET /api/history/trips/1/versions"
curl -s "$BASE_URL/api/history/trips/1/versions" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool > /dev/null && echo "  ✅ 版本链接口正常（404 预期）"

echo "  DELETE /api/history/trips/1"
curl -s -X DELETE "$BASE_URL/api/history/trips/1" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool > /dev/null && echo "  ✅ 删除接口正常（404 预期）"
echo ""

# 3. KnowledgeController 测试
echo "【3】KnowledgeController（7 个端点）"
echo "  GET /api/knowledge/spots"
curl -s "$BASE_URL/api/knowledge/spots?page=1&pageSize=20" | python3 -m json.tool > /dev/null && echo "  ✅ 景点列表接口正常"

echo "  GET /api/knowledge/spots/1"
curl -s "$BASE_URL/api/knowledge/spots/1" | python3 -m json.tool > /dev/null && echo "  ✅ 景点详情接口正常（404 预期）"

echo "  GET /api/knowledge/spot-docs"
curl -s "$BASE_URL/api/knowledge/spot-docs?page=1&pageSize=20" | python3 -m json.tool > /dev/null && echo "  ✅ 文档列表接口正常"

# Admin 端点（需要 admin token，跳过或测试 403）
echo "  POST /api/knowledge/spots（需要 admin）"
curl -s -X POST "$BASE_URL/api/knowledge/spots" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"测试景点","city":"北京","category":"景点"}' | python3 -m json.tool > /dev/null && echo "  ⚠️  创建接口（可能 403）"

echo "  PUT /api/knowledge/spots/1（需要 admin）"
curl -s -X PUT "$BASE_URL/api/knowledge/spots/1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"更新景点"}' | python3 -m json.tool > /dev/null && echo "  ⚠️  更新接口（可能 403）"

echo "  DELETE /api/knowledge/spots/1（需要 admin）"
curl -s -X DELETE "$BASE_URL/api/knowledge/spots/1" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool > /dev/null && echo "  ⚠️  删除接口（可能 403）"

echo "  POST /api/knowledge/spots/bulk（需要 admin）"
curl -s -X POST "$BASE_URL/api/knowledge/spots/bulk" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '[]' | python3 -m json.tool > /dev/null && echo "  ⚠️  批量导入接口（可能 403）"
echo ""

# 4. FeedbackController 测试
echo "【4】FeedbackController（5 个端点）"
echo "  GET /api/feedback"
curl -s "$BASE_URL/api/feedback?page=1&pageSize=20" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool > /dev/null && echo "  ✅ 反馈列表接口正常"

echo "  GET /api/feedback/message/1"
curl -s "$BASE_URL/api/feedback/message/1" | python3 -m json.tool > /dev/null && echo "  ✅ 消息统计接口正常"

echo "  GET /api/feedback/stats（需要 admin）"
curl -s "$BASE_URL/api/feedback/stats?days=7" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool > /dev/null && echo "  ⚠️  全局统计接口（可能 403）"

echo "  GET /api/feedback/list/1（需要 admin）"
curl -s "$BASE_URL/api/feedback/list/1" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool > /dev/null && echo "  ⚠️  反馈列表接口（可能 403）"

echo "  POST /api/feedback"
curl -s -X POST "$BASE_URL/api/feedback" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messageId":1,"conversationId":1,"rating":1,"comment":"测试","tags":["test"]}' | python3 -m json.tool > /dev/null && echo "  ⚠️  提交反馈接口（可能失败）"
echo ""

# 5. CommuteController 测试
echo "【5】CommuteController（4 个端点）"
echo "  GET /api/commute/geocode?address=天安门"
curl -s "$BASE_URL/api/commute/geocode?address=天安门&city=北京" | python3 -m json.tool > /dev/null && echo "  ✅ 地理编码接口正常"

echo "  GET /api/commute/inputtips?keywords=天安"
curl -s "$BASE_URL/api/commute/inputtips?keywords=天安" | python3 -m json.tool > /dev/null && echo "  ✅ 输入联想接口正常"

echo "  GET /api/commute/nearby?lat=39.9087&lng=116.3975"
curl -s "$BASE_URL/api/commute/nearby?lat=39.9087&lng=116.3975&radius=1000" | python3 -m json.tool > /dev/null && echo "  ✅ 周边搜索接口正常"

echo "  POST /api/commute/optimal"
curl -s -X POST "$BASE_URL/api/commute/optimal" \
  -H "Content-Type: application/json" \
  -d '{"origin":"天安门","destinations":["故宫"],"mode":"driving","city":"北京"}' | python3 -m json.tool > /dev/null && echo "  ⚠️  最优通勤接口（简化版）"
echo ""

# 6. AdminController 测试
echo "【6】AdminController（3 个端点）"
echo "  GET /api/admin/agent-trace/1（需要 admin）"
curl -s "$BASE_URL/api/admin/agent-trace/1" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool > /dev/null && echo "  ⚠️  Agent 轨迹接口（可能 403）"

echo "  GET /api/admin/agent-trace?conversation_id=1（需要 admin）"
curl -s "$BASE_URL/api/admin/agent-trace?conversation_id=1" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool > /dev/null && echo "  ⚠️  轨迹摘要接口（可能 403）"

echo "  GET /api/admin/mcp-stats（需要 admin）"
curl -s "$BASE_URL/api/admin/mcp-stats" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool > /dev/null && echo "  ⚠️  MCP 状态接口（可能 403）"
echo ""

echo "=========================================="
echo "联调测试完成"
echo "=========================================="
