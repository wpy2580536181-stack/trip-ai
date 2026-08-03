package com.trip.backend.eval.runner;

import com.trip.backend.eval.types.FixtureResult;
import com.trip.backend.eval.types.ReportSummary;

import java.util.List;

/**
 * 控制台输出辅助
 */
public class ConsolePrinter {

    /**
     * 打印详细结果
     */
    public static void printResults(List<FixtureResult> results) {
        System.out.println("\n=== 详细结果 ===\n");
        for (FixtureResult r : results) {
            String status = r.isPassed() ? "✓ PASS" : "✗ FAIL";
            System.out.printf("%s  %-45s  %s%n",
                    status, r.getFixtureId(),
                    r.getDescription() != null ? r.getDescription() : "");
        }
    }

    /**
     * 打印汇总
     */
    public static void printSummary(ReportSummary summary) {
        System.out.println("\n=== 汇总 ===\n");

        int passed = summary.getPassedFixtures();
        int total = summary.getTotalFixtures();
        double passRate = summary.getPassRate();
        String passRateStr = String.format("%.1f", passRate * 100);

        // 根据通过率选择颜色（简化版：无颜色）
        String marker = passRate == 1.0 ? "✓" : (passRate >= 0.8 ? "△" : "✗");
        System.out.printf("%s  %d/%d 通过 (%s%%)  %dms%n",
                marker, passed, total, passRateStr, summary.getTotalDurationMs());

        // 按 tag 统计
        if (summary.getByTag() != null && !summary.getByTag().isEmpty()) {
            System.out.println("\n按 tag:");
            summary.getByTag().forEach((tag, stats) -> {
                String tagRate = String.format("%.0f%%", stats.getPassRate() * 100);
                System.out.printf("  %-25s  %d/%d (%s)%n",
                        tag, stats.getPassed(), stats.getTotal(), tagRate);
            });
        }

        // 按 evaluator 统计
        if (summary.getByEvaluator() != null && !summary.getByEvaluator().isEmpty()) {
            System.out.println("\n按 evaluator:");
            summary.getByEvaluator().forEach((name, stats) -> {
                String evalRate = String.format("%.0f%%", stats.getPassRate() * 100);
                System.out.printf("  %-30s  %d/%d (%s)%n",
                        name, stats.getPassed(), stats.getTotal(), evalRate);
            });
        }
    }
}
