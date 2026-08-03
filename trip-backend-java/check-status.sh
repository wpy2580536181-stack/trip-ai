#!/bin/bash
# Java 后端启动监控脚本

echo "🔍 监控 Java 后端启动进度..."
echo "PID: $(cat /tmp/java-backend.pid 2>/dev/null || echo 'N/A')"
echo ""

# 检查进程
if ps -p $(cat /tmp/java-backend.pid 2>/dev/null) > /dev/null 2>&1; then
  echo "✅ Maven 进程正在运行"
else
  echo "❌ Maven 进程已停止"
  exit 1
fi

# 检查日志最新进度
echo ""
echo "📊 最新下载进度："
tail -1 /tmp/java-backend.log | grep "Progress" || echo "暂无进度信息"

# 检查是否启动成功
echo ""
echo "🔍 检查启动状态..."
if curl -s http://localhost:8000/health | grep -q "OK"; then
  echo "✅ Java 后端已就绪！"
  exit 0
else
  echo "⏳ Java 后端尚未就绪（继续等待...）"
fi

# 检查日志中的错误
echo ""
echo "📋 最近日志（错误/警告）："
grep -E "Error|Exception|FAIL|started|Started" /tmp/java-backend.log | tail -10
