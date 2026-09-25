package com.trip.backend.service.agent;

import org.springframework.beans.factory.annotation.Autowired;

import com.trip.backend.domain.entity.AgentStep;
import com.trip.backend.domain.repository.AgentStepRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

/**
 * 轨迹记录器（对应 Python trace_recorder.py）。
 *
 *  - buffer：step 先入内存（避免 N+1）
 *  - flush：agent 完成后批量落 agent_steps（step/type/name/args/output/duration_ms/error）
 *  - 失败只 warn，不影响业务
 *  - message_id<=0 跳过落库（无关联消息）
 */
public class TraceRecorder {

    private static final Logger log = LoggerFactory.getLogger(TraceRecorder.class);

    /** flush 时批量写入（生产 = repo::saveAll；测试可断言）。 */
    public interface BatchSaver {
        void saveAll(List<AgentStep> rows);
    }

    private final long messageId;
    private final List<AgentStep> buffer = new ArrayList<>();
    private final BatchSaver saver;

    public TraceRecorder(Long messageId, AgentStepRepository repo) {
        this(messageId == null ? 0L : messageId, repo::saveAll);
    }

    public TraceRecorder(long messageId, BatchSaver saver) {
        this.messageId = messageId;
        this.saver = saver;
    }

    /** 记录一条 step（buffer）。 */
    public synchronized void add(int step, String type, String name,
                                 Map<String, Object> args, String output,
                                 Long durationMs, String error) {
        AgentStep row = new AgentStep();
        row.setMessageId(messageId);
        row.setStep(step);
        row.setType(type);
        row.setName(name);
        row.setArgs(args);
        row.setOutput(output);
        row.setDurationMs(durationMs);
        row.setError(error);
        buffer.add(row);
    }

    /** 便捷：只带 type/name。 */
    public void add(int step, String type, String name) {
        add(step, type, name, null, null, null, null);
    }

    /** 批量落库；失败只 warn。返回本次写入条数。 */
    public synchronized int flush() {
        if (buffer.isEmpty()) {
            return 0;
        }
        if (messageId <= 0) {
            log.warn("agent trace 跳过落库: message_id<=0（无关联消息），count={}", buffer.size());
            int n = buffer.size();
            buffer.clear();
            return n;
        }
        try {
            List<AgentStep> snapshot = new ArrayList<>(buffer);
            saver.saveAll(snapshot);
            buffer.clear();
            return snapshot.size();
        } catch (Exception e) {
            log.warn("agent trace flush 失败: {}", e.getMessage());
            return 0;
        }
    }

    /** 当前 buffer 内 step 数（测试/调试）。 */
    public synchronized int pending() {
        return buffer.size();
    }
}
