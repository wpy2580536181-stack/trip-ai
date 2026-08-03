package com.trip.backend.eval.registry;

import com.trip.backend.eval.Evaluator;
import com.trip.backend.eval.types.EvalResult;
import com.trip.backend.eval.types.Fixture;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Evaluator 注册表
 */
public class EvaluatorRegistry {
    private static final Map<String, Evaluator> REGISTRY = new HashMap<>();

    /**
     * 注册 evaluator
     */
    public static void register(String name, Evaluator evaluator) {
        REGISTRY.put(name, evaluator);
    }

    /**
     * 获取 evaluator
     */
    public static Optional<Evaluator> get(String name) {
        return Optional.ofNullable(REGISTRY.get(name));
    }

    /**
     * 获取所有已注册的 evaluator 名称
     */
    public static List<String> listAll() {
        return REGISTRY.keySet().stream().sorted().toList();
    }

    /**
     * 清空注册表（用于测试）
     */
    public static void clear() {
        REGISTRY.clear();
    }
}
