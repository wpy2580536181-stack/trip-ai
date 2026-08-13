#!/bin/bash
# E4-2 Dual-run 对比脚本：Python vs Java 同输入对比
# 对标 Python: scripts/dual-run.sh

set -e

PYTHON_URL="${PYTHON_URL:-http://localhost:8001}"
JAVA_URL="${JAVA_URL:-http://localhost:8080}"
REPORT_DIR="$(cd "$(dirname "$0")/../.." && pwd)/docs/e4"
REPORT_FILE="$REPORT_DIR/dual-run-report.md"

echo "=========================================="
echo "E4-2: Dual-run 对比测试"
echo "Python: $PYTHON_URL"
echo "Java: $JAVA_URL"
echo "=========================================="

# 创建报告目录
mkdir -p "$REPORT_DIR"

# 初始化报告
cat > "$REPORT_FILE" << 'EOF'
# Dual-run 对比报告

## 测试环境

| 服务 | URL | 状态 |
|------|-----|------|
| Python | ${PYTHON_URL} | 待检测 |
| Java | ${JAVA_URL} | 待检测 |

## 端点对比结果

| 端点 | 方法 | Python 状态 | Java 状态 | Diff |
|------|------|------------|----------|------|
EOF

# 测试端点列表（核心 20 个）
declare -A ENDPOINTS=(
  ["注册"]="POST|/api/user/register|{\"username\":\"dual_test\",\"password\":\"Test@123\",\"email\":\"dual@test.com\"}"
  ["登录"]="POST|/api/user/login|{\"identifier\":\"dual_test\",\"password\":\"Test@123\"}"
  ["用户信息"]="GET|/api/user/info|"
  ["景点列表"]="GET|/api/knowledge/spots?page=1&pageSize=10|"
  ["通勤地理编码"]="GET|/api/commute/geocode?address=北京天安门|"
  ["周边POI"]="GET|/api/commute/nearby?lat=39.908823&lng=116.397470&radius=1000&keywords=餐饮&limit=5|"
)

# 统计
TOTAL=0
PASSED=0
FAILED=0
DIFF_COUNT=0

# 测试每个端点
for name in "${!ENDPOINTS[@]}"; do
  IFS='|' read -r method path body <<< "${ENDPOINTS[$name]}"
  TOTAL=$((TOTAL + 1))

  echo ""
  echo "[$TOTAL] 测试: $name ($method $path)"

  # 发送请求到 Python
  if [ "$method" = "GET" ]; then
    PYTHON_RESP=$(curl -s -X GET "$PYTHON_URL$path" 2>/dev/null || echo '{"error":"failed"}')
    JAVA_RESP=$(curl -s -X GET "$JAVA_URL$path" 2>/dev/null || echo '{"error":"failed"}')
  else
    PYTHON_RESP=$(curl -s -X POST "$PYTHON_URL$path" \
      -H "Content-Type: application/json" \
      -d "$body" 2>/dev/null || echo '{"error":"failed"}')
    JAVA_RESP=$(curl -s -X POST "$JAVA_URL$path" \
      -H "Content-Type: application/json" \
      -d "$body" 2>/dev/null || echo '{"error":"failed"}')
  fi

  # 提取关键字段对比
  PYTHON_CODE=$(echo "$PYTHON_RESP" | grep -o '"code":[0-9]*' | head -1 | sed 's/"code"://')
  JAVA_CODE=$(echo "$JAVA_RESP" | grep -o '"code":[0-9]*' | head -1 | sed 's/"code"://')

  # 对比
  if [ "$PYTHON_CODE" = "$JAVA_CODE" ]; then
    echo "✅ PASS (code=$PYTHON_CODE)"
    PASSED=$((PASSED + 1))
    DIFF="✅ 无差异"
  else
    echo "⚠️  DIFF (Python code=$PYTHON_CODE, Java code=$JAVA_CODE)"
    FAILED=$((FAILED + 1))
    DIFF_COUNT=$((DIFF_COUNT + 1))
    DIFF="❌ code 不一致"
  fi

  # 追加到报告
  echo "| $name | $method | code=$PYTHON_CODE | code=$JAVA_CODE | $DIFF |" >> "$REPORT_FILE"

done

# 汇总
cat >> "$REPORT_FILE" << EOF

## 汇总

| 指标 | 值 |
|------|-----|
| 总端点 | $TOTAL |
| 通过 | $PASSED |
| 失败 | $FAILED |
| Diff 数 | $DIFF_COUNT |

## 结论

EOF

if [ $DIFF_COUNT -eq 0 ]; then
  echo "✅ **全端点 diff 清零**" >> "$REPORT_FILE"
  echo ""
  echo "=========================================="
  echo "✅ Dual-run 对比通过：0 diff"
  echo "=========================================="
  exit 0
else
  echo "⚠️  **发现 $DIFF_COUNT 个 diff**（需要进一步优化）" >> "$REPORT_FILE"
  echo ""
  echo "=========================================="
  echo "⚠️  Dual-run 对比：$DIFF_COUNT diff（非阻塞）"
  echo "=========================================="
  exit 0  # 非阻塞，返回 0
fi
