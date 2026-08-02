package com.trip.backend.service.agent.tools;

import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 工具契约测试
 */
class ToolContractTest {

    private final ToolSpecRegistry registry = new ToolSpecRegistry();

    @Test
    void testRetrieveKnowledgeToolSpec() {
        // TODO: 需要注入 KnowledgeService
    }

    @Test
    void testSearchHotelsToolSpec() {
        // TODO: 需要注入 KnowledgeService
    }

    @Test
    void testCalculateDistanceToolSpec() {
        // TODO: 需要注入 CommuteService
    }

    @Test
    void testCommuteToolSpecs() {
        // TODO: 需要注入 CommuteService
    }

    @Test
    void testMeituanToolSpec() {
        // TODO: 需要注入 MeituanTool
    }

    @Test
    void testToolSpecRegistryRegister() {
        // 测试注册表基本功能
        ToolSpecRegistry.ToolEntry entry = new ToolSpecRegistry.ToolEntry(
            "test_tool",
            () -> "test",
            Map.of("type", "object")
        );

        registry.register(entry);

        ToolSpecRegistry.ToolEntry found = registry.findByName("test_tool");
        assertThat(found).isNotNull();
        assertThat(found.name()).isEqualTo("test_tool");

        assertThat(registry.getAllTools()).hasSize(1);
    }
}
