package com.trip.backend.eval;

import com.trip.backend.eval.loader.FixtureLoader;
import com.trip.backend.eval.runner.ConsolePrinter;
import com.trip.backend.eval.runner.EvalRunner;
import com.trip.backend.eval.types.ReportSummary;

import java.nio.file.Path;
import java.util.List;

/**
 * Eval CLI 入口
 *
 * 用法：
 *   java -cp ... com.trip.backend.eval.Main [--samples N]
 *
 * 环境变量：
 *   EVAL_FIXTURES_DIR  fixtures 目录路径
 *   EVAL_VERBOSE       详细输出
 */
public class Main {

    public static void main(String[] args) {
        // 解析参数（简化版：仅支持 --samples N）
        int samples = 1;
        for (int i = 0; i < args.length; i++) {
            if ("--samples".equals(args[i]) && i + 1 < args.length) {
                try {
                    samples = Integer.parseInt(args[i + 1]);
                } catch (NumberFormatException e) {
                    System.err.println("Invalid samples value: " + args[i + 1]);
                    System.exit(2);
                }
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
            EvalRunner runner = new EvalRunner(fixturesDir);
            ReportSummary summary = runner.runAll(verbose);

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
}
