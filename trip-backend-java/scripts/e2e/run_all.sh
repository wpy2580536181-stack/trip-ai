#!/bin/bash
# E4-1 前端全流程回归测试 - 总入口
# 运行所有 6 个核心流程测试

set -e

BASE_URL="${BASE_URL:-http://localhost:8080}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=========================================="
echo "E4-1: 前端全流程回归测试"
echo "BASE_URL: $BASE_URL"
echo "=========================================="

# 检查服务是否可用
echo ""
echo "检查 Java 服务健康状态..."
HEALTH_RESP=$(curl -s "$BASE_URL/health")

if [ "$HEALTH_RESP" != "OK" ]; then
  echo "❌ Java 服务未启动或健康检查失败"
  echo "请先启动服务：mvn spring-boot:run"
  exit 1
fi

echo "✅ Java 服务健康"

# 运行所有测试脚本
FAILED=0

echo ""
echo "=========================================="
echo "开始运行测试脚本..."
echo "=========================================="

# 测试 1: 注册/登录
echo ""
if bash "$SCRIPT_DIR/test_register_login.sh"; then
  echo "✅ 注册/登录流程 PASS"
else
  echo "❌ 注册/登录流程 FAIL"
  FAILED=$((FAILED + 1))
fi

# 测试 2: Chat 对话
echo ""
if bash "$SCRIPT_DIR/test_chat_flow.sh"; then
  echo "✅ Chat 对话流程 PASS"
else
  echo "❌ Chat 对话流程 FAIL"
  FAILED=$((FAILED + 1))
fi

# 测试 3: Recommend 推荐
echo ""
if bash "$SCRIPT_DIR/test_recommend_flow.sh"; then
  echo "✅ Recommend 推荐流程 PASS"
else
  echo "❌ Recommend 推荐流程 FAIL"
  FAILED=$((FAILED + 1))
fi

# 测试 4: 历史/管理
echo ""
if bash "$SCRIPT_DIR/test_history.sh"; then
  echo "✅ 历史/管理流程 PASS"
else
  echo "❌ 历史/管理流程 FAIL"
  FAILED=$((FAILED + 1))
fi

# 测试 5: 知识库/反馈
echo ""
if bash "$SCRIPT_DIR/test_knowledge.sh"; then
  echo "✅ 知识库/反馈流程 PASS"
else
  echo "❌ 知识库/反馈流程 FAIL"
  FAILED=$((FAILED + 1))
fi

# 测试 6: 通勤查询
echo ""
if bash "$SCRIPT_DIR/test_commute.sh"; then
  echo "✅ 通勤查询流程 PASS"
else
  echo "❌ 通勤查询流程 FAIL"
  FAILED=$((FAILED + 1))
fi

# 汇总结果
echo ""
echo "=========================================="
echo "测试结果汇总"
echo "=========================================="
echo "失败数: $FAILED / 6"

if [ $FAILED -eq 0 ]; then
  echo "✅ 全部测试通过"
  exit 0
else
  echo "❌ 部分测试失败"
  exit 1
fi
