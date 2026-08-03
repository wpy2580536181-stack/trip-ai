package com.trip.backend.eval.runner;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.eval.EvalUtils;
import com.trip.backend.eval.Evaluator;
import com.trip.backend.eval.agents.MockAgent;
import com.trip.backend.eval.registry.EvaluatorRegistry;
import com.trip.backend.eval.types.AgentOutput;
import com.trip.backend.eval.types.EvalResult;
import com.trip.backend.eval.types.Fixture;
import com.trip.backend.eval.types.FixtureResult;
import com.trip.backend.eval.types.GroupStats;
import com.trip.backend.eval.types.ReportSummary;
import com.trip.backend.eval.loader.FixtureLoader;

import java.nio.file.Path;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Eval 运行器
 */
public class EvalRunner {

    private final Path fixturesDir;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public EvalRunner(Path fixturesDir) {
        this.fixturesDir = fixturesDir;
    }

    /**
     * 运行所有 fixture
     */
    public ReportSummary runAll(boolean verbose) {
        List<Fixture> fixtures;
        try {
            fixtures = FixtureLoader.loadFromDirectory(fixturesDir);
        } catch (Exception e) {
            System.err.println("Failed to load fixtures: " + e.getMessage());
            return createEmptySummary();
        }

        List<FixtureResult> results = new ArrayList<>();
        for (Fixture fixture : fixtures) {
            results.add(runSingle(fixture, verbose));
        }

        return summarize(results);
    }

    /**
     * 运行单个 fixture
     */
    public FixtureResult runSingle(Fixture fixture, boolean verbose) {
        long startTime = System.currentTimeMillis();

        try {
            // 1. 执行 agent
            AgentOutput output = MockAgent.run(fixture);

            // 2. 执行所有 evaluator
            Map<String, EvalResult> evaluatorResults = new LinkedHashMap<>();
            boolean allPassed = true;

            for (String evaluatorName : fixture.getEvaluators()) {
                Optional<Evaluator> evaluatorOpt = EvaluatorRegistry.get(evaluatorName);
                if (evaluatorOpt.isEmpty()) {
                    evaluatorResults.put(evaluatorName, EvalResult.fail("Evaluator not found: " + evaluatorName));
                    allPassed = false;
                    continue;
                }

                try {
                    EvalResult result = evaluatorOpt.get().evaluate(output, fixture);
                    evaluatorResults.put(evaluatorName, result);
                    if (!result.isPassed()) {
                        allPassed = false;
                    }
                } catch (Exception e) {
                    evaluatorResults.put(evaluatorName, EvalResult.fail("Evaluator error: " + e.getMessage()));
                    allPassed = false;
                }
            }

            long durationMs = System.currentTimeMillis() - startTime;

            if (verbose) {
                String status = allPassed ? "✓ PASS" : "✗ FAIL";
                System.out.printf("  %s  %-45s  %dms%n", status, fixture.getId(), durationMs);
            }

            return new FixtureResult(
                    fixture.getId(),
                    fixture.getDescription(),
                    String.join(", ", fixture.getTags()),
                    allPassed,
                    output,
                    evaluatorResults,
                    durationMs,
                    null
            );

        } catch (Exception e) {
            long durationMs = System.currentTimeMillis() - startTime;
            if (verbose) {
                System.out.printf("  ✗ ERROR  %-45s  %dms  %s%n", fixture.getId(), durationMs, e.getMessage());
            }
            return new FixtureResult(
                    fixture.getId(),
                    fixture.getDescription(),
                    String.join(", ", fixture.getTags()),
                    false,
                    null,
                    Map.of(),
                    durationMs,
                    e.getMessage()
            );
        }
    }

    /**
     * 汇总结果
     */
    public ReportSummary summarize(List<FixtureResult> results) {
        int total = results.size();
        int passed = (int) results.stream().filter(FixtureResult::isPassed).count();
        long totalDuration = results.stream().mapToLong(FixtureResult::getDurationMs).sum();

        // 按 tag 统计
        Map<String, GroupStats> byTag = new LinkedHashMap<>();
        // 按 evaluator 统计
        Map<String, GroupStats> byEvaluator = new LinkedHashMap<>();

        for (FixtureResult result : results) {
            // 按 tag
            String[] tags = result.getTags().split(",");
            for (String tag : tags) {
                tag = tag.trim();
                if (tag.isEmpty()) continue;
                byTag.computeIfAbsent(tag, k -> new GroupStats()).total++;
                if (result.isPassed()) {
                    byTag.get(tag).passed++;
                }
            }

            // 按 evaluator
            for (Map.Entry<String, EvalResult> entry : result.getEvaluatorResults().entrySet()) {
                String evalName = entry.getKey();
                EvalResult evalResult = entry.getValue();
                byEvaluator.computeIfAbsent(evalName, k -> new GroupStats()).total++;
                if (evalResult.isPassed()) {
                    byEvaluator.get(evalName).passed++;
                }
            }
        }

        return new ReportSummary(total, passed, total - passed, totalDuration,
                total > 0 ? (double) passed / total : 0.0, byTag, byEvaluator, null);
    }

    private ReportSummary createEmptySummary() {
        return new ReportSummary(0, 0, 0, 0, 0.0, Map.of(), Map.of(), null);
    }
}
