package com.trip.backend.eval.runner;

import com.trip.backend.eval.agents.MockAgent;
import com.trip.backend.eval.agents.RealAgent;
import com.trip.backend.eval.types.AgentOutput;
import com.trip.backend.eval.types.EvalResult;
import com.trip.backend.eval.types.Fixture;
import com.trip.backend.eval.types.FixtureResult;
import com.trip.backend.eval.registry.EvaluatorRegistry;
import com.trip.backend.eval.Evaluator;
import com.trip.backend.eval.loader.FixtureLoader;

import java.nio.file.Path;
import java.util.*;
import java.util.stream.Collectors;

/**
 * 多采样运行器
 * <p>
 * 对同一 fixture 运行多次，取多数结果（majority vote）
 */
public class MultiSampleRunner {

    private final Path fixturesDir;
    private final int samples;
    private final boolean useRealAgent;
    private final String backendUrl;

    /**
     * 构造函数
     *
     * @param fixturesDir   fixture 目录
     * @param samples       采样次数
     * @param useRealAgent  是否使用真实 agent
     * @param backendUrl    后端 URL（仅 useRealAgent=true 时需要）
     */
    public MultiSampleRunner(Path fixturesDir, int samples, boolean useRealAgent, String backendUrl) {
        this.fixturesDir = fixturesDir;
        this.samples = Math.max(1, samples);
        this.useRealAgent = useRealAgent;
        this.backendUrl = backendUrl;
    }

    /**
     * 运行所有 fixture（多采样）
     */
    public List<FixtureResult> runAll(boolean verbose) throws Exception {
        List<Fixture> fixtures = FixtureLoader.loadFromDirectory(fixturesDir);
        List<FixtureResult> results = new ArrayList<>();

        for (Fixture fixture : fixtures) {
            results.add(runSingle(fixture, verbose));
        }

        return results;
    }

    /**
     * 运行单个 fixture（多采样）
     */
    public FixtureResult runSingle(Fixture fixture, boolean verbose) {
        long startTime = System.currentTimeMillis();

        try {
            // 1. 执行多次采样
            List<AgentOutput> outputs = new ArrayList<>();
            for (int i = 0; i < samples; i++) {
                AgentOutput output;
                if (useRealAgent) {
                    RealAgent realAgent = new RealAgent(backendUrl);
                    output = realAgent.run(fixture, false);
                } else {
                    output = MockAgent.run(fixture);
                }
                outputs.add(output);
            }

            // 2. 对每个 evaluator 执行多采样评估
            Map<String, EvalResult> evaluatorResults = new LinkedHashMap<>();
            boolean allPassed = true;

            for (String evaluatorName : fixture.getEvaluators()) {
                Optional<Evaluator> evaluatorOpt = EvaluatorRegistry.get(evaluatorName);
                if (evaluatorOpt.isEmpty()) {
                    evaluatorResults.put(evaluatorName, EvalResult.fail("Evaluator not found: " + evaluatorName));
                    allPassed = false;
                    continue;
                }

                // 多采样：多数投票
                List<EvalResult> sampleResults = new ArrayList<>();
                for (AgentOutput output : outputs) {
                    try {
                        EvalResult result = evaluatorOpt.get().evaluate(output, fixture);
                        sampleResults.add(result);
                    } catch (Exception e) {
                        sampleResults.add(EvalResult.fail("Evaluator error: " + e.getMessage()));
                    }
                }

                // 统计通过次数
                long passCount = sampleResults.stream().filter(EvalResult::isPassed).count();
                boolean majorityPass = passCount > samples / 2;

                if (!majorityPass) {
                    allPassed = false;
                }

                // 记录多采样结果
                Map<String, Object> details = new HashMap<>();
                details.put("pass_count", passCount);
                details.put("total_samples", samples);
                details.put("pass_rate", (double) passCount / samples);
                evaluatorResults.put(evaluatorName, new EvalResult(majorityPass,
                    String.format("%d/%d samples passed", passCount, samples), details));
            }

            long durationMs = System.currentTimeMillis() - startTime;

            if (verbose) {
                String status = allPassed ? "✓ PASS" : "✗ FAIL";
                System.out.printf("  %s  %-45s  %dms (%d samples)%n",
                    status, fixture.getId(), durationMs, samples);
            }

            // 使用第一次采样的输出作为代表
            AgentOutput representativeOutput = outputs.get(0);

            return new FixtureResult(
                    fixture.getId(),
                    fixture.getDescription(),
                    String.join(", ", fixture.getTags()),
                    allPassed,
                    representativeOutput,
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
}
