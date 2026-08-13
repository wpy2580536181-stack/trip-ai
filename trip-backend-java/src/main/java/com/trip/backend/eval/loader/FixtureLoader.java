package com.trip.backend.eval.loader;

import java.util.Collections;
import java.util.List;

/**
 * Fixture 加载器（骨架实现）
 *
 * 对应 Python: eval/runner.py (load_fixtures)
 */
public class FixtureLoader {

    /**
     * 加载 fixtures 目录下的所有 YAML 文件
     *
     * @param fixturesDir fixtures 目录路径
     * @return Fixture 列表（暂时返回空列表）
     */
    public static List<?> loadFixtures(String fixturesDir) {
        System.out.println("⚠️  FixtureLoader 待完善（需要实现 YAML 解析 + 类型定义）");
        return Collections.emptyList();
    }
}
