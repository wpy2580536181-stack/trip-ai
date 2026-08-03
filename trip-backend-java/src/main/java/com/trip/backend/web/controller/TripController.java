package com.trip.backend.web.controller;

import com.trip.backend.service.TripService;
import com.trip.backend.service.agent.dto.PlanRequest;
import com.trip.backend.utils.AppException;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.io.PrintWriter;
import java.util.Map;

/**
 * Trip 控制器（recommend 链路 - G4 简化实现）
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

    private final TripService tripService;

    public TripController(TripService tripService) {
        this.tripService = tripService;
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
            // 调用 TripService.recommend()
            Map<String, Object> result = tripService.recommend(
                userId,
                request.city(),
                request.budget() != null ? request.budget() : 0,
                request.days() != null ? request.days() : 1
            );

            return ResponseEntity.ok(result);

        } catch (AppException e) {
            throw e;
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
    public void recommendStream(
            @RequestAttribute("userId") Long userId,
            @Valid @RequestBody PlanRequest request,
            HttpServletResponse response) throws IOException {

        String streamId = java.util.UUID.randomUUID().toString();

        response.setContentType("text/event-stream");
        response.setCharacterEncoding("UTF-8");
        response.setHeader("Cache-Control", "no-cache");
        response.setHeader("Connection", "keep-alive");
        response.setHeader("X-Accel-Buffering", "no");
        response.setHeader("X-Stream-Id", streamId);

        PrintWriter writer = response.getWriter();

        try {
            // 1. Send start event
            writer.write("data: " + toJson(Map.of(
                "type", "start",
                "city", request.city(),
                "days", request.days(),
                "budget", request.budget()
            )) + "\n\n");
            writer.flush();

            // 2. 模拟 progress 事件（实际应该从 Orchestrator 透传）
            writer.write("data: " + toJson(Map.of(
                "type", "progress",
                "stage", "research",
                "status", "start"
            )) + "\n\n");
            writer.flush();

            writer.write("data: " + toJson(Map.of(
                "type", "progress",
                "stage", "research",
                "status", "done"
            )) + "\n\n");
            writer.flush();

            writer.write("data: " + toJson(Map.of(
                "type", "progress",
                "stage", "plan",
                "status", "start"
            )) + "\n\n");
            writer.flush();

            // 3. 调用 TripService（这里应该调用带事件回调的版本）
            // TODO: TripService.recommendWithEvents() 实现后调用
            Map<String, Object> result = tripService.recommend(
                userId,
                request.city(),
                request.budget() != null ? request.budget() : 0,
                request.days() != null ? request.days() : 1
            );

            writer.write("data: " + toJson(Map.of(
                "type", "progress",
                "stage", "plan",
                "status", "done"
            )) + "\n\n");
            writer.flush();

            writer.write("data: " + toJson(Map.of(
                "type", "progress",
                "stage", "review",
                "status", "start"
            )) + "\n\n");
            writer.flush();

            writer.write("data: " + toJson(Map.of(
                "type", "progress",
                "stage", "review",
                "status", "done"
            )) + "\n\n");
            writer.flush();

            writer.write("data: " + toJson(Map.of(
                "type", "progress",
                "stage", "save",
                "status", "start"
            )) + "\n\n");
            writer.flush();

            // 4. Send complete event with result
            writer.write("data: " + toJson(Map.of(
                "type", "complete",
                "data", result
            )) + "\n\n");
            writer.flush();

            writer.write("data: " + toJson(Map.of(
                "type", "progress",
                "stage", "save",
                "status", "done"
            )) + "\n\n");
            writer.flush();

            // 5. Send end event
            writer.write("data: " + toJson(Map.of("type", "end")) + "\n\n");
            writer.flush();

        } catch (Exception e) {
            try {
                writer.write("data: " + toJson(Map.of(
                    "type", "error",
                    "error", e.getMessage()
                )) + "\n\n");
                writer.flush();
            } catch (Exception ex) {
                // ignore
            }
        } finally {
            writer.close();
        }
    }

    /**
     * POST /trip/{id}/confirm
     */
    @PostMapping("/{id}/confirm")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> confirmTrip(
            @RequestAttribute("userId") Long userId,
            @PathVariable Long id) {
        return ResponseEntity.ok(Map.of(
            "success", true,
            "message", "Trip confirmed"
        ));
    }

    /**
     * POST /trip/{id}/discard
     */
    @PostMapping("/{id}/discard")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> discardTrip(
            @RequestAttribute("userId") Long userId,
            @PathVariable Long id) {
        return ResponseEntity.ok(Map.of(
            "success", true,
            "message", "Trip discarded"
        ));
    }

    private String toJson(Object obj) {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(obj);
        } catch (Exception e) {
            throw new RuntimeException("Failed to serialize JSON", e);
        }
    }
}
