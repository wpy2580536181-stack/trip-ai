package com.trip.backend.service.rag;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * RRF 融合测试
 */
class RrfTest {

    private final Rrf rrf = new Rrf();

    @Test
    void testRrfMerge() {
        // 准备测试数据
        List<Map<String, Object>> path1 = List.of(
            Map.of("id", "1", "name", "故宫"),
            Map.of("id", "2", "name", "长城")
        );
        List<Map<String, Object>> path2 = List.of(
            Map.of("id", "2", "name", "长城"),
            Map.of("id", "3", "name", "天安门")
        );

        List<List<Map<String, Object>>> results = List.of(path1, path2);

        // 执行 RRF
        List<Map<String, Object>> merged = rrf.merge(results, 60, "id");

        // 验证：id=2 应该排第一（两个路径都召回）
        assertThat(merged).isNotEmpty();
        assertThat(merged.get(0).get("id")).isEqualTo("2");
        assertThat(merged.get(0)).containsKey("_rrf_score");
    }

    @Test
    void testRrfMergeWithWeights() {
        List<Map<String, Object>> path1 = List.of(
            Map.of("id", "1", "name", "故宫"),
            Map.of("id", "2", "name", "长城")
        );
        List<Map<String, Object>> path2 = List.of(
            Map.of("id", "2", "name", "长城"),
            Map.of("id", "3", "name", "天安门")
        );

        List<List<Map<String, Object>>> results = List.of(path1, path2);
        List<Double> weights = List.of(0.7, 0.5);

        // 执行加权 RRF
        List<Map<String, Object>> merged = rrf.mergeWithWeights(results, weights, 60, "id");

        // 验证结果
        assertThat(merged).isNotEmpty();
        assertThat(merged.get(0).get("id")).isEqualTo("2");
    }

    @Test
    void testRrfEmptyInput() {
        List<List<Map<String, Object>>> empty = List.of();
        List<Map<String, Object>> result = rrf.merge(empty, 60, "id");
        assertThat(result).isEmpty();
    }

    @Test
    void testRrfSinglePath() {
        List<Map<String, Object>> path = List.of(
            Map.of("id", "1", "name", "故宫"),
            Map.of("id", "2", "name", "长城")
        );

        List<Map<String, Object>> merged = rrf.merge(List.of(path), 60, "id");

        assertThat(merged).hasSize(2);
        assertThat(merged.get(0).get("id")).isEqualTo("1");
    }
}
