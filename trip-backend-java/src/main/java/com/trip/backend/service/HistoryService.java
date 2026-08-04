package com.trip.backend.service;

import com.trip.backend.domain.entity.Trip;
import com.trip.backend.domain.repository.TripRepository;
import com.trip.backend.utils.AppException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;

/**
 * History service（对应 Python services/history_service.py）
 * - 行程历史查询
 * - 版本链查询
 * - 删除行程
 */
@Service
public class HistoryService {

    private final TripRepository tripRepository;

    public HistoryService(TripRepository tripRepository) {
        this.tripRepository = tripRepository;
    }

    /**
     * 获取行程历史列表（分页）
     *
     * @param userId 用户ID
     * @param page 页码（1-based）
     * @param pageSize 每页数量
     * @return Page<Trip>
     */
    @Transactional(readOnly = true)
    public Page<Trip> getTrips(Long userId, int page, int pageSize) {
        // 排除 parent_trip_id 不为空的行程（只显示根行程）
        return tripRepository.findByUserIdAndParentTripIdIsNull(
            userId,
            PageRequest.of(page - 1, pageSize)
        );
    }

    /**
     * 获取单个行程详情
     *
     * @param tripId 行程ID
     * @param userId 用户ID（权限校验）
     * @return Trip 对象
     * @throws AppException 404 如果行程不存在或无权限
     */
    @Transactional(readOnly = true)
    public Trip getTrip(Long tripId, Long userId) {
        return tripRepository.findByIdAndUserId(tripId, userId)
            .orElseThrow(() -> new AppException("行程不存在或无权访问", 404));
    }

    /**
     * 获取行程版本链（V1...Vn，根版本在前）
     *
     * 从 tripId 沿 parentTripId 回溯到根，再从根逐层收集全部子版本
     * （同层按 createdAt 升序展平）。深度上限 20，防脏数据成环。
     *
     * @param tripId 行程ID（链中任意节点）
     * @param userId 用户ID（权限校验）
     * @return 按版本顺序（根在前）的行程列表
     * @throws AppException 404 如果行程不存在或无权限
     */
    @Transactional(readOnly = true)
    public List<Trip> getTripVersions(Long tripId, Long userId) {
        // 1. 验证权限
        Trip trip = getTrip(tripId, userId);

        // 2. 向上回溯到根（带深度上限 + 成环防护）
        Trip root = trip;
        List<Long> visited = new ArrayList<>();
        visited.add(root.getId());

        for (int i = 0; i < 20; i++) {
            if (root.getParentTripId() == null) {
                break;
            }

            Trip parent = tripRepository.findByIdAndUserId(root.getParentTripId(), userId)
                .orElse(null);

            if (parent == null || visited.contains(parent.getId())) {
                break;
            }

            visited.add(parent.getId());
            root = parent;
        }

        // 3. 从根逐层向下收集（同层按 createdAt 升序）
        List<Trip> versions = new ArrayList<>();
        versions.add(root);

        List<Long> frontier = new ArrayList<>();
        frontier.add(root.getId());

        for (int i = 0; i < 20; i++) {
            if (frontier.isEmpty()) {
                break;
            }

            // 查询 frontier 的所有子节点（按 createdAt 升序）
            List<Trip> children = tripRepository.findByParentTripIdInAndUserIdOrderByCreatedAtAsc(
                frontier,
                userId
            );

            // 过滤已收集的节点
            List<Trip> newChildren = children.stream()
                .filter(child -> !visited.contains(child.getId()))
                .toList();

            if (newChildren.isEmpty()) {
                break;
            }

            versions.addAll(newChildren);
            visited.addAll(newChildren.stream().map(Trip::getId).toList());
            frontier = new ArrayList<>(newChildren.stream().map(Trip::getId).toList());
        }

        return versions;
    }

    /**
     * 删除行程
     *
     * @param tripId 行程ID
     * @param userId 用户ID（权限校验）
     * @throws AppException 404 如果行程不存在或无权限
     */
    @Transactional
    public void deleteTrip(Long tripId, Long userId) {
        // 1. 验证权限
        Trip trip = getTrip(tripId, userId);

        // 2. 删除行程（级联删除子行程、对话、消息、agent_steps）
        tripRepository.delete(trip);
    }
}
