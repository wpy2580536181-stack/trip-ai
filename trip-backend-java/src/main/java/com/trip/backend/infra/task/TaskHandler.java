package com.trip.backend.infra.task;

import java.util.Map;

/**
 * 任务处理器（对应 Python arq worker 函数 `async def func(ctx, *args, **kwargs)`）。
 *
 * 实现方注册到 {@link TaskRegistry}，由队列消费端按 taskName 查找执行。
 */
@FunctionalInterface
public interface TaskHandler {

    /**
     * 执行任务。
     *
     * @param args 任务参数（JSON 对象，入队时原样透传）
     * @return 任务结果（写入结果存储，供 getResult 读取）
     * @throws Exception 执行失败（触发重试策略）
     */
    Map<String, Object> execute(Map<String, Object> args) throws Exception;
}
