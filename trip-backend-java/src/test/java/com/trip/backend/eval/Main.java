package com.trip.backend.eval;

import com.trip.backend.eval.loader.FixtureLoader;
import com.trip.backend.eval.runner.ConsolePrinter;
import com.trip.backend.eval.runner.EvalRunner;
import com.trip.backend.eval.runner.MultiSampleRunner;
import com.trip.backend.eval.types.ReportSummary;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.LinkedHashMap;
import java.util.Optional;

/**
 * Eval CLI 入口
 *
 * 用法：
 *   java -cp ... com.trip.backend.eval.Main [--samples N] [--real] [--url URL]
 *
 * 环境变量：
 *   EVAL_FIXTURES_DIR  fixtures 目录路径
 *   EVAL_VERBOSE       详细输出
 *   BACKEND_URL        后端 URL（默认 http://localhost:8080）
 */
public class Main {

    public static void main(String[] args) {
        // 解析参数
        int samples = 1;
        boolean useRealAgent = false;
        String backendUrl = System.getenv().getOrDefault("BACKEND_URL", "http://localhost:8080");

        for (int i = 0; i < args.length; i++) {
            if ("--samples".equals(args[i]) && i + 1 < args.length) {
                try {
                    samples = Integer.parseInt(args[i + 1]);
                } catch (NumberFormatException e) {
                    System.err.println("Invalid samples value: " + args[i + 1]);
                    System.exit(2);
                }
            } else if ("--real".equals(args[i])) {
                useRealAgent = true;
            } else if ("--url".equals(args[i]) && i + 1 < args.length) {
                backendUrl = args[i + 1];
            }
        }

        // 确定 fixtures 目录
        String fixturesDirStr = System.getenv().getOrDefault("EVAL_FIXTURES_DIR",
                "src/test/resources/eval/fixtures");
        Path fixturesDir = Path.of(fixturesDirStr);

        boolean verbose = "true".equalsIgnoreCase(System.getenv().getOrDefault("EVAL_VERBOSE", "false"));

        System.out.println("=== Trip Agent Eval (Java) ===");
        System.out.println("fixtures: " + fixturesDir);
        System.out.println("samples: " + samples + (samples > 1 ? " (majority vote)" : " (single)"));
        System.out.println("agent: " + (useRealAgent ? "Real (" + backendUrl + ")" : "Mock"));
        System.out.println();

        try {
            // 加载所有 fixture
            List<com.trip.backend.eval.types.Fixture> fixtures = FixtureLoader.loadFromDirectory(fixturesDir);
            System.out.println("将跑 " + fixtures.size() + " 个 fixture\n");

            if (fixtures.isEmpty()) {
                System.err.println("No fixtures found in " + fixturesDir);
                System.exit(2);
            }

            // 运行 eval
            MultiSampleRunner runner = new MultiSampleRunner(fixturesDir, samples, useRealAgent, backendUrl);
            List<com.trip.backend.eval.types.FixtureResult> results = runner.runAll(verbose);

            // 汇总结果
            com.trip.backend.eval.types.ReportSummary summary = summarize(results);

            // 打印结果
            ConsolePrinter.printSummary(summary);

            // 退出码：0 = 全部通过，1 = 有失败
            System.exit(summary.getFailedFixtures() == 0 ? 0 : 1);

        } catch (Exception e) {
            System.err.println("Eval runner error: " + e.getMessage());
            e.printStackTrace();
            System.exit(2);
        }
    }

    /**
     * 汇总结果
     */
    private static com.trip.backend.eval.types.ReportSummary summarize(List<com.trip.backend.eval.types.FixtureResult> results) {
        int total = results.size();
        int passed = (int) results.stream().filter(com.trip.backend.eval.types.FixtureResult::isPassed).count();
        long totalDuration = results.stream().mapToLong(com.trip.backend.eval.types.FixtureResult::getDurationMs).sum();

        // 按 tag 统计
        Map<String, com.trip.backend.eval.types.GroupStats> byTag = new LinkedHashMap<>();
        // 按 evaluator 统计
        Map<String, com.trip.backend.eval.types.GroupStats> byEvaluator = new LinkedHashMap<>();

        for (com.trip.backend.eval.types.FixtureResult result : results) {
            // 按 tag
            String[] tags = result.getTags().split(",");
            for (String tag : tags) {
                tag = tag.trim();
                if (tag.isEmpty()) continue;
                byTag.computeIfAbsent(tag, k -> new com.trip.backend.eval.types.GroupStats()).total++;
                if (result.isPassed()) {
                    byTag.get(tag).passed++;
                }
            }

            // 按 evaluator
            for (Map.Entry<String, com.trip.backend.eval.types.EvalResult> entry : result.getEvaluatorResults().entrySet()) {
                String evalName = entry.getKey();
                com.trip.backend.eval.types.EvalResult evalResult = entry.getValue();
                byEvaluator.computeIfAbsent(evalName, k -> new com.trip.backend.eval.types.GroupStats()).total++;
                if (evalResult.isPassed()) {
                    byEvaluator.get(evalName).passed++;
                }
            }
        }

        return new com.trip.backend.eval.types.ReportSummary(total, passed, total - passed, totalDuration,
                total > 0 ? (double) passed / total : 0.0, byTag, byEvaluator, null);
    }
}
