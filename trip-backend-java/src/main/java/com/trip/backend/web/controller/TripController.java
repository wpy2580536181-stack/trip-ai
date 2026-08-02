package com.trip.backend.web.controller;

import com.trip.backend.domain.dto.PlanRequest;
import com.trip.backend.service.AgentEngine;
import com.trip.backend.service.agent.PlanResult;
import com.trip.backend.web.sse.SseEvent;
import com.trip.backend.web.sse.SseWriter;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.Map;

/**
 * Trip 控制器（recommend 链路）
 *
 * 端点：
 * - POST /trip/recommend（非流式，Format A）
 * - POST /trip/recommend-stream（SSE 流式）
 * - POST /trip/{id}/confirm（确认行程）
 * - POST /trip/{id}/discard（丢弃行程）
 */
@RestController
@RequestMapping("/api/trip")
public class TripController {

    private final AgentEngine agentEngine;
    private final SseWriter sseWriter;

    public TripController(AgentEngine agentEngine, SseWriter sseWriter) {
        this.agentEngine = agentEngine;
        this.sseWriter = sseWriter;
    }

    /**
     * POST /trip/recommend
     *
     * 非流式推荐（Format A）
     */
    @PostMapping(value = "/recommend", consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> recommend(
            @RequestAttribute("userId") Long userId,
            @Valid @RequestBody PlanRequest request) {

        try {
            PlanResult result = agentEngine.recommend(request).join();

            // Format A: {success, data}
            Map<String, Object> response = Map.of(
                "success", true,
                "data", result.plan()
            );

            return ResponseEntity.ok(response);

        } catch (Exception e) {
            return ResponseEntity.ok(Map.of(
                "success", false,
                "error", e.getMessage()
            ));
        }
    }

    /**
     * POST /trip/recommend-stream
     *
     * 流式推荐（SSE）
     */
    @PostMapping(value = "/recommend-stream", consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<SseEmitter> recommendStream(
            @RequestAttribute("userId") Long userId,
            @Valid @RequestBody PlanRequest request) {

        String streamId = java.util.UUID.randomUUID().toString();

        SseEmitter emitter = new SseEmitter(0L);

        new Thread(() -> {
            try {
                sseWriter.attach(emitter);

                // 发送 start 事件
                sseWriter.send(SseEvent.of(streamId, "start", String.format(
                    "{\"city\":\"%s\",\"days\":%d,\"budget\":%d}",
                    request.city(), request.days(), request.budget()
                )));

                // 调用 AgentEngine
                agentEngine.recommend(request).whenComplete((result, error) -> {
                    try {
                        if (error != null) {
                            sseWriter.send(SseEvent.of(streamId, "error", String.format(
                                "{\"error\":\"%s\"}", error.getMessage()
                            )));
                        } else {
                            // 发送 complete 事件
                            sseWriter.send(SseEvent.of(streamId, "complete", "{}"));
                        }
                        sseWriter.send(SseEvent.end(streamId));
                        sseWriter.close();
                    } catch (Exception e) {
                        sseWriter.close();
                    }
                });

            } catch (Exception e) {
                try {
                    sseWriter.send(SseEvent.of(streamId, "error", String.format(
                        "{\"error\":\"%s\"}", e.getMessage()
                    )));
                    sseWriter.send(SseEvent.end(streamId));
                    sseWriter.close();
                } catch (Exception ex) {
                    // 忽略
                }
            }
        }).start();

        return ResponseEntity.ok()
            .header("X-Stream-Id", streamId)
            .header("Cache-Control", "no-cache")
            .header("Connection", "keep-alive")
            .header("X-Accel-Buffering", "no")
            .body(emitter);
    }

    /**
     * POST /trip/{id}/confirm
     *
     * 确认行程（candidate → completed）
     */
    @PostMapping("/{id}/confirm")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> confirmTrip(
            @RequestAttribute("userId") Long userId,
            @PathVariable Long id) {

        // TODO: D11 实现后补充
        return ResponseEntity.ok(Map.of(
            "success", true,
            "message", "Trip confirmed"
        ));
    }

    /**
     * POST /trip/{id}/discard
     *
     * 丢弃行程（candidate → discarded）
     */
    @PostMapping("/{id}/discard")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> discardTrip(
            @RequestAttribute("userId") Long userId,
            @PathVariable Long id) {

        // TODO: D11 实现后补充
        return ResponseEntity.ok(Map.of(
            "success", true,
            "message", "Trip discarded"
        ));
    }
}
