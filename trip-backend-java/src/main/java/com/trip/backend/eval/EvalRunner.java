package com.trip.backend.eval;

import java.util.List;
import java.util.Map;

/**
 * EvalRunner: Eval 框架主入口（简化版）
 *
 * 对应 Python: eval/runner.py
 */
public class EvalRunner {

    private final RealAgent realAgent;

    public EvalRunner(String baseUrl) {
        this.realAgent = new RealAgent(baseUrl);
    }

    /**
     * 运行单个 fixture
     */
    public Map<String, Object> runFixture(Map<String, Object> fixture) {
        String id = (String) fixture.get("id");
        System.out.println("\n运行 fixture: " + id);

        // 提取 input.message
        Map<String, Object> input = (Map<String, Object>) fixture.get("input");
        String message = (String) input.getOrDefault("message", "");

        // 调用 Agent
        System.out.println("  调用 Agent: " + message.substring(0, Math.min(50, message.length())) + "...");
        Map<String, Object> agentOutput = realAgent.call(message);

        // 运行 evaluators
        List<String> evaluators = (List<String>) fixture.get("evaluators");
        if (evaluators == null || evaluators.isEmpty()) {
            return Map.of(
                "id", id,
                "passed", false,
                "error", "无 evaluator"
            );
        }

        // 运行所有 evaluator（简化版：全部返回 false）
        int passed = 0;
        int failed = 0;

        for (String evaluatorName : evaluators) {
            Map<String, Object> result = EvaluatorRegistry.evaluate(evaluatorName, fixture, agentOutput);
            boolean evalPassed = (Boolean) result.getOrDefault("passed", false);

            if (evalPassed) {
                passed++;
                System.out.println("  ✅ " + evaluatorName);
            } else {
                failed++;
                System.out.println("  ❌ " + evaluatorName + ": " + result.get("reason"));
            }
        }

        boolean allPassed = failed == 0;
        System.out.println("  结果: " + passed + "/" + evaluators.size() + " 通过");

        return Map.of(
            "id", id,
            "passed", allPassed,
            "passedCount", passed,
            "totalCount", evaluators.size(),
            "agentOutput", agentOutput
        );
    }

    /**
     * 运行所有 fixture
     */
    public List<Map<String, Object>> runAll(List<Map<String, Object>> fixtures) {
        List<Map<String, Object>> results = new java.util.ArrayList<>();

        for (Map<String, Object> fixture : fixtures) {
            Map<String, Object> result = runFixture(fixture);
            results.add(result);
        }

        return results;
    }

    /**
     * 打印汇总报告
     */
    public void printSummary(List<Map<String, Object>> results) {
        int total = results.size();
        long passed = results.stream().filter(r -> (Boolean) r.get("passed")).count();
        long failed = total - passed;
        double passRate = total > 0 ? (double) passed / total : 0.0;

        System.out.println("\n========================================");
        System.out.println("Eval 汇总报告");
        System.out.println("========================================");
        System.out.println("总数: " + total);
        System.out.println("通过: " + passed);
        System.out.println("失败: " + failed);
        System.out.printf("通过率: %.1f%%\n", passRate * 100);
        System.out.println("========================================\n");

        // 输出失败的 fixture
        System.out.println("失败详情:");
        for (Map<String, Object> result : results) {
            if (!(Boolean) result.get("passed")) {
                System.out.println("  ❌ " + result.get("id"));
            }
        }
    }
}
