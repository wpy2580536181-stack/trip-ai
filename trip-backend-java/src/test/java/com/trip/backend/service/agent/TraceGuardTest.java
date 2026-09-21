package com.trip.backend.service.agent;

import com.trip.backend.domain.entity.AgentStep;
import com.trip.backend.middleware.ConcurrencyGuard;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-D10 判定：
 *  1. 10 并发 chat → 第 11 个收到 429（ConcurrencyLimitException）
 *  2. 中途断开客户端后信号量释放，后续请求可正常进入
 *  3. agent_steps 表字段完整、顺序正确
 */
class TraceGuardTest {

    // ---- 判定 1：10 并发 → 第 11 个 429 ----
    @Test
    void tenAcquiredEleventhRejected() throws Exception {
        ConcurrencyGuard guard = new ConcurrencyGuard(10, 1);
        // 占满全局 10 个许可（不同 userId，避免每用户信号量互斥）
        for (int i = 0; i < 10; i++) {
            guard.acquire((long) i);
        }
        // 第 11 个 → 超限
        assertThrows(ConcurrencyGuard.ConcurrencyLimitException.class,
            () -> guard.acquire(999L), "第 11 个应被拒（映射 HTTP 429）");
    }

    // ---- 判定 2：断开（release）后槽位归还，后续可进 ----
    @Test
    void releaseFreesSlotForNextRequest() throws Exception {
        ConcurrencyGuard guard = new ConcurrencyGuard(10, 1);
        for (int i = 0; i < 10; i++) {
            guard.acquire((long) i);
        }
        assertThrows(ConcurrencyGuard.ConcurrencyLimitException.class, () -> guard.acquire(999L));

        // 模拟客户端中途断开 → finally 释放一个槽位
        guard.release(0L);

        // 后续请求可正常进入
        guard.acquire(1000L);
        // 又满了 → 下一个再拒
        assertThrows(ConcurrencyGuard.ConcurrencyLimitException.class, () -> guard.acquire(1001L));
    }

    // ---- 判定 3：agent_steps 字段完整、顺序正确 ----
    @Test
    void traceBufferFlushesInOrderWithAllFields() {
        List<AgentStep> saved = new ArrayList<>();
        TraceRecorder recorder = new TraceRecorder(42L, saved::addAll);

        recorder.add(1, "tool_start", "retrieveKnowledge",
            Map.of("q", "故宫"), null, null, null);
        recorder.add(2, "tool_end", "retrieveKnowledge",
            null, "[7136,659]", 120L, null);
        recorder.add(3, "error", "planner",
            null, null, null, "timeout");

        assertEquals(3, recorder.pending());
        int flushed = recorder.flush();
        assertEquals(3, flushed);
        assertEquals(3, saved.size());
        assertEquals(0, recorder.pending());

        // 顺序 = add 顺序
        assertEquals(1, saved.get(0).getStep());
        assertEquals("tool_start", saved.get(0).getType());
        assertEquals(2, saved.get(1).getStep());
        assertEquals(3, saved.get(2).getStep());

        // 字段完整
        AgentStep s1 = saved.get(0);
        assertEquals(42L, s1.getMessageId());
        assertEquals("retrieveKnowledge", s1.getName());
        assertEquals("故宫", s1.getArgs().get("q"));

        AgentStep s2 = saved.get(1);
        assertEquals("[7136,659]", s2.getOutput());
        assertEquals(120L, s2.getDurationMs());

        AgentStep s3 = saved.get(2);
        assertEquals("timeout", s3.getError());
    }

    @Test
    void messageIdZeroSkipsDbWriteButKeepsBuffer() {
        AtomicInteger writes = new AtomicInteger();
        TraceRecorder recorder = new TraceRecorder(0L, rows -> writes.incrementAndGet());
        recorder.add(1, "complete", "chat");
        int n = recorder.flush();
        assertEquals(1, n, "buffer 仍清空并返回条数");
        assertEquals(0, writes.get(), "message_id<=0 不真写库");
    }
}
