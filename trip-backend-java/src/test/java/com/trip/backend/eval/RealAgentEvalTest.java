package com.trip.backend.eval;

import com.trip.backend.eval.agents.RealAgent;
import com.trip.backend.eval.loader.FixtureLoader;
import com.trip.backend.eval.types.*;
import com.trip.backend.eval.util.TestAuthHelper;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Real Agent Eval 集成测试
 */
class RealAgentEvalTest {

    @Test
    void testRealAgentWithSingleFixture() throws Exception {
        // 获取测试 token
        String token = TestAuthHelper.getTestToken();
        assertNotNull(token, "需要有效的测试 token");

        // 加载 fixture
        Path fixturesDir = Path.of("src/test/resources/eval/fixtures/trip-planning");
        List<Fixture> fixtures = FixtureLoader.loadFromDirectory(fixturesDir);

        // 取第一个 fixture
        Fixture first = fixtures.get(0);
        System.out.println("Testing fixture: " + first.getId());

        // 创建 RealAgent
        RealAgent agent = new RealAgent("http://localhost:8000", token);

        // 执行 agent
        AgentOutput output = agent.run(first, false);

        // 验证输出不为空
        assertNotNull(output, "Agent 输出不应为 null");
        assertNotNull(output.getJson(), "Agent JSON 不应为 null");

        System.out.println("Agent output JSON: " + output.getJson());
        System.out.println("Duration: " + output.getDurationMs() + "ms");

        // 至少应该有一些评估通过（不强制，用于观察）
        System.out.println("Real agent test completed");
    }
}
