package com.trip.backend.infra.task;

import org.springframework.stereotype.Component;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.Map;

/**
 * 任务注册表（对应 Python arq worker 注册：func.__name__ → func）。
 *
 * 任务名（taskName）→ 处理器。J-C4 / D12 通过 register() 挂载自己的 worker。
 */
@Component
public class TaskRegistry {

    private final Map<String, TaskHandler> handlers = new ConcurrentHashMap<>();

    /** 注册任务处理器（同名覆盖）。 */
    public void register(String taskName, TaskHandler handler) {
        if (taskName == null || taskName.isBlank()) {
            throw new IllegalArgumentException("taskName must not be blank");
        }
        handlers.put(taskName, handler);
    }

    /** 按任务名查找处理器。 */
    public Optional<TaskHandler> get(String taskName) {
        return Optional.ofNullable(handlers.get(taskName));
    }

    public boolean contains(String taskName) {
        return handlers.containsKey(taskName);
    }

    public Map<String, TaskHandler> all() {
        return Map.copyOf(handlers);
    }
}
