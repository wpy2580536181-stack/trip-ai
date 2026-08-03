package com.trip.backend.eval;

import com.trip.backend.eval.evaluators.GeneralEvaluators;
import com.trip.backend.eval.loader.FixtureLoader;
import com.trip.backend.eval.runner.EvalRunner;
import com.trip.backend.eval.runner.ConsolePrinter;
import com.trip.backend.eval.registry.EvaluatorRegistry;
import com.trip.backend.eval.agents.MockAgent;
import com.trip.backend.eval.agents.RealAgent;
import com.trip.backend.eval.types.AgentOutput;
import com.trip.backend.eval.types.EvalResult;
import com.trip.backend.eval.types.Fixture;
import com.trip.backend.eval.types.FixtureExpected;
import com.trip.backend.eval.types.ReportSummary;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Eval 框架单元测试
 */
class EvaluatorTest {

    @Test
    void testEvaluatorRegistry() {
        // 加载所有 evaluators 类（触发 static 初始化）
        try {
            Class.forName("com.trip.backend.eval.evaluators.DomainEvaluators");
            Class.forName("com.trip.backend.eval.evaluators.MultiTurnEvaluators");
        } catch (ClassNotFoundException e) {
            fail("Failed to load evaluator classes: " + e.getMessage());
        }

        // 验证 13 个 evaluator 已注册
        List<String> evaluators = EvaluatorRegistry.listAll();
        assertEquals(13, evaluators.size());

        // 验证几个核心 evaluator
        assertTrue(EvaluatorRegistry.get("schema_check").isPresent());
        assertTrue(EvaluatorRegistry.get("poi_city_match").isPresent());
        assertTrue(EvaluatorRegistry.get("keyword_coverage").isPresent());
        assertTrue(EvaluatorRegistry.get("tool_call_audit").isPresent());
        assertTrue(EvaluatorRegistry.get("pace_consistency").isPresent());
    }

    @Test
    void testSchemaCheck() {
        // 准备测试数据
        AgentOutput output = new AgentOutput();
        output.setJson(Map.of("city", "成都", "days", 3, "dailyItinerary", List.of(), "budgetBreakdown", Map.of(), "totalBudget", 3000));

        FixtureExpected expected = new FixtureExpected();
        expected.setJsonValid(true);

        Fixture fixture = new Fixture();
        fixture.setExpected(expected);

        EvalResult result = GeneralEvaluators.schemaCheck(output, fixture);
        assertTrue(result.isPassed());
    }

    @Test
    void testKeywordCoverage() {
        AgentOutput output = new AgentOutput();
        output.setText("成都美食之旅，包含火锅和茶馆");

        FixtureExpected expected = new FixtureExpected();
        expected.setMustContainKeywords(List.of("火锅", "茶馆"));
        expected.setMustNotContainKeywords(List.of("酒吧"));
        expected.setKeywordMatchMode("all");

        Fixture fixture = new Fixture();
        fixture.setExpected(expected);

        EvalResult result = GeneralEvaluators.keywordCoverage(output, fixture);
        assertTrue(result.isPassed());
    }

    @Test
    void testKeywordCoverageFail() {
        AgentOutput output = new AgentOutput();
        output.setText("成都美食之旅，包含火锅");

        FixtureExpected expected = new FixtureExpected();
        expected.setMustContainKeywords(List.of("火锅", "茶馆"));
        expected.setKeywordMatchMode("all");

        Fixture fixture = new Fixture();
        fixture.setExpected(expected);

        EvalResult result = GeneralEvaluators.keywordCoverage(output, fixture);
        assertFalse(result.isPassed());
    }

    @Test
    void testFixtureLoader() throws Exception {
        Path fixturesDir = Path.of("src/test/resources/eval/fixtures/trip-planning");
        List<Fixture> fixtures = FixtureLoader.loadFromDirectory(fixturesDir);

        assertFalse(fixtures.isEmpty());
        assertEquals(10, fixtures.size());

        // 验证第一个 fixture（按字母排序，beijing 在 chengdu 前）
        Fixture first = fixtures.get(0);
        assertEquals("beijing-3days-halal-vegetarian", first.getId());
        assertFalse(first.getEvaluators().isEmpty());
    }

    @Test
    void testEvalRunner() throws Exception {
        // 确保 evaluator 已注册
        Class.forName("com.trip.backend.eval.evaluators.GeneralEvaluators");
        Class.forName("com.trip.backend.eval.evaluators.DomainEvaluators");
        Class.forName("com.trip.backend.eval.evaluators.MultiTurnEvaluators");

        Path fixturesDir = Path.of("src/test/resources/eval/fixtures/trip-planning");
        EvalRunner runner = new EvalRunner(fixturesDir);

        ReportSummary summary = runner.runAll(true);

        assertNotNull(summary);
        assertEquals(10, summary.getTotalFixtures());
        // Mock agent 应该能通过 >= 50% 的测试
        assertTrue(summary.getPassRate() >= 0.5, "Mock agent 通过率应该 >= 50%, 实际: " + String.format("%.0f%%", summary.getPassRate() * 100));
    }

    @Test
    void testMockAgentEvaluation() throws Exception {
        // 确保 evaluator 已注册
        Class.forName("com.trip.backend.eval.evaluators.GeneralEvaluators");
        Class.forName("com.trip.backend.eval.evaluators.DomainEvaluators");
        Class.forName("com.trip.backend.eval.evaluators.MultiTurnEvaluators");

        Path fixturesDir = Path.of("src/test/resources/eval/fixtures/trip-planning");
        List<Fixture> fixtures = FixtureLoader.loadFromDirectory(fixturesDir);

        assertEquals(13, EvaluatorRegistry.listAll().size());

        Fixture first = fixtures.get(0);
        AgentOutput output = MockAgent.run(first);

        // 验证至少部分 evaluator 通过
        int passCount = 0;
        for (String evaluatorName : first.getEvaluators()) {
            Optional<Evaluator> evaluatorOpt = EvaluatorRegistry.get(evaluatorName);
            assertTrue(evaluatorOpt.isPresent(), "Evaluator should be registered: " + evaluatorName);
            EvalResult result = evaluatorOpt.get().evaluate(output, first);
            if (result.isPassed()) passCount++;
        }

        assertTrue(passCount > 0, "至少应该有一些 evaluator 通过");
    }

    @Test
    void testRealAgentCompilation() {
        // 测试 RealAgent 可以实例化（不实际调用后端）
        RealAgent agent = new RealAgent("http://localhost:8080");
        assertNotNull(agent);
    }
}
