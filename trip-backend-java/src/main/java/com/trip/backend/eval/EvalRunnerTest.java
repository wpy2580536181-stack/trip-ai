package com.trip.backend.eval;

import java.util.List;
import java.util.Map;

/**
 * EvalRunner 测试类（快速验证）
 */
public class EvalRunnerTest {

    public static void main(String[] args) {
        System.out.println("========================================");
        System.out.println("EvalRunner 测试");
        System.out.println("========================================\n");

        // 测试 RealAgent
        System.out.println("[1/3] 测试 RealAgent...");
        RealAgent agent = new RealAgent("http://localhost:8080");
        Map<String, Object> output = agent.call("你好，请帮我规划一个北京 3 日游");
        System.out.println("响应: " + output.get("text"));
        System.out.println("错误: " + output.get("error"));

        // 测试 EvaluatorRegistry
        System.out.println("\n[2/3] 测试 EvaluatorRegistry...");
        System.out.println("已注册 evaluator: " + EvaluatorRegistry.listEvaluators());

        // 测试 EvalRunner
        System.out.println("\n[3/3] 测试 EvalRunner...");
        EvalRunner runner = new EvalRunner("http://localhost:8080");

        // 构造测试 fixture
        Map<String, Object> fixture = Map.of(
            "id", "test-001",
            "description", "测试用例",
            "input", Map.of("message", "北京 3 日游"),
            "evaluators", List.of("schema_check", "keyword_coverage")
        );

        Map<String, Object> result = runner.runFixture(fixture);
        System.out.println("结果: " + result);

        runner.printSummary(List.of(result));

        System.out.println("\n✅ EvalRunner 测试完成");
    }
}
