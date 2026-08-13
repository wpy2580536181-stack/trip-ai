package com.trip.backend.eval.loader;

import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * FixtureLoader: 加载 fixture（纯 Map 实现，无外部依赖）
 */
public class FixtureLoader {

    /**
     * 加载所有 fixture（简化版）
     */
    public static List<Map<String, Object>> loadFixtures(String fixturesDir) {
        System.out.println("⚠️  FixtureLoader 待实现 SnakeYAML 集成");
        System.out.println("   当前返回空列表");
        return Collections.emptyList();
    }
}
