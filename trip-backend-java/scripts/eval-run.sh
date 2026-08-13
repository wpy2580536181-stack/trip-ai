#!/bin/bash
# E4-3 Eval 双回归验证脚本
# 对标 Python: scripts/eval-run.sh

set -e

BASE_URL="${EVAL_BASE_URL:-http://localhost:8080}"
REPORT_DIR="$(cd "$(dirname "$0")/../.." && pwd)/docs/e4"
REPORT_FILE="$REPORT_DIR/java-eval-report.md"
BASELINE_FILE="$(cd "$(dirname "$0")/../.." && pwd)/docs/eval/python-baseline.json"

echo "=========================================="
echo "E4-3: Eval 双回归验证"
echo "BASE_URL: $BASE_URL"
echo "=========================================="

# 检查服务是否可用
echo ""
echo "检查服务健康状态..."
HEALTH=$(curl -s "$BASE_URL/health")

if [ "$HEALTH" != "OK" ]; then
  echo "❌ 服务未启动（$BASE_URL）"
  exit 1
fi

echo "✅ 服务健康"

# 创建报告目录
mkdir -p "$REPORT_DIR"

# 初始化报告
cat > "$REPORT_FILE" << EOF
# Java Eval 评估报告

## 测试环境

- **BASE_URL**: $BASE_URL
- **Python 基线**: $BASELINE_FILE
- **测试时间**: $(date '+%Y-%m-%d %H:%M:%S')

## 评估结果

| Fixture | 状态 | Java 结果 | Python 基线 |
|---------|------|----------|-----------|
EOF

# TODO: 运行 eval 框架（需要实现 Java eval runner）
# 暂时输出占位符
echo ""
echo "⚠️  Eval 框架实现待完善"
echo ""
echo "当前状态："
echo "  - Python Mock Agent: 100% (10/10) ✅"
echo "  - Java Mock Agent: 待实现"
echo ""
echo "下一步："
echo "  1. 实现 Java EvalRunner（对标 Python eval/run.py）"
echo "  2. 运行 10 个 fixture"
echo "  3. 生成对比报告"

# 占位符：添加 baseline 对比
if [ -f "$BASELINE_FILE" ]; then
  echo ""
  echo "📊 Python 基线数据（参考）："
  cat "$BASELINE_FILE" | head -20
fi

cat >> "$REPORT_FILE" << EOF

## 结论

⚠️ **Eval 框架待完善**（优先级 P1）

### Python 基线数据（参考）

- **总通过率**: 8/10 (80%)
- **Token hitRate**: 80.9% (13,440/16,608)

### 失败 Fixture

- `shanghai-2days-with-pet` - pet_constraint_check 失败
- `rejection-no-trip-output` - keyword_coverage 失败

### 后续行动

1. **立即**: 实现 Java EvalRunner（调用真实 API）
2. **然后**: 运行双回归验证
3. **目标**: pass_rate ≥ 80%（对齐 Python 基线）

EOF

echo ""
echo "报告已生成: $REPORT_FILE"
echo "⚠️  Eval 双回归待后续完善"
