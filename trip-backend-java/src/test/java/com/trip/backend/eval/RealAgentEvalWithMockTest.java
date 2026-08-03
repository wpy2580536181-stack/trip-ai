package com.trip.backend.eval;

import com.trip.backend.eval.agents.MockAgent;
import com.trip.backend.eval.agents.RealAgent;
import com.trip.backend.eval.loader.FixtureLoader;
import com.trip.backend.eval.types.*;
import com.trip.backend.eval.util.TestAuthHelper;
import com.trip.backend.eval.registry.EvaluatorRegistry;
import com.trip.backend.eval.Evaluator;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.*;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Real Agent Eval 测试（使用 Mock Agent 模拟真实后端的完整响应）
 *
 * 注意：由于后端依赖 LLM API key，暂时使用 Mock Agent 验证 eval 流程
 * 待 LLM 配置完成后切换到真实 Agent
 */
class RealAgentEvalWithMockTest {

    @Test
    void testMockAgentAsRealAgent() throws Exception {
        // 确保 evaluator 已注册
        Class.forName("com.trip.backend.eval.evaluators.GeneralEvaluators");
        Class.forName("com.trip.backend.eval.evaluators.DomainEvaluators");
        Class.forName("com.trip.backend.eval.evaluators.MultiTurnEvaluators");

        // 加载 fixture
        Path fixturesDir = Path.of("src/test/resources/eval/fixtures/trip-planning");
        List<Fixture> fixtures = FixtureLoader.loadFromDirectory(fixturesDir);
        assertEquals(10, fixtures.size());

        System.out.println("\n=== Mock Agent Eval 完整验证 ===\n");
        System.out.println("Fixtures: " + fixtures.size());
        System.out.println("Evaluators: " + EvaluatorRegistry.listAll().size());

        int passCount = 0;
        StringBuilder report = new StringBuilder();

        for (Fixture fixture : fixtures) {
            // 使用 Mock Agent（模拟完整行程响应）
            AgentOutput output = MockAgent.run(fixture);

            // 评估
            boolean fixturePassed = true;
            StringBuilder evalDetails = new StringBuilder();

            for (String evaluatorName : fixture.getEvaluators()) {
                Optional<Evaluator> evaluatorOpt = EvaluatorRegistry.get(evaluatorName);
                if (evaluatorOpt.isPresent()) {
                    try {
                        EvalResult result = evaluatorOpt.get().evaluate(output, fixture);
                        if (!result.isPassed()) {
                            fixturePassed = false;
                            evalDetails.append(String.format("  ✗ %-30s  %s%n",
                                evaluatorName, result.getReason()));
                        }
                    } catch (Exception e) {
                        fixturePassed = false;
                        evalDetails.append(String.format("  ✗ %-30s  ERROR: %s%n",
                            evaluatorName, e.getMessage()));
                    }
                }
            }

            if (fixturePassed) {
                passCount++;
                System.out.printf("✓ %-45s%n", fixture.getId());
                report.append(String.format("✓ %-45s%n", fixture.getId()));
            } else {
                System.out.printf("✗ %-45s%n", fixture.getId());
                System.out.print(evalDetails);
                report.append(String.format("✗ %-45s%n", fixture.getId()));
                report.append(evalDetails);
            }
        }

        double passRate = passCount * 100.0 / fixtures.size();
        System.out.printf("%n通过率: %d/%d (%.0f%%)%n", passCount, fixtures.size(), passRate);
        System.out.println("Python 基线: 80% (8/10)");
        System.out.println("Mock Agent: " + String.format("%.0f%%", passRate) + " (" + passCount + "/" + fixtures.size() + ")");

        // 保存报告到文件
        String reportFile = "target/eval-report-mock-agent.txt";
        java.nio.file.Files.writeString(Path.of(reportFile), report.toString());
        System.out.println("报告已保存: " + reportFile);

        // 验证 Mock Agent 至少达到 50%（作为 baseline）
        assertTrue(passRate >= 50.0, "Mock Agent 通过率应 >= 50%, 实际: " + String.format("%.0f%%", passRate));
    }
}
