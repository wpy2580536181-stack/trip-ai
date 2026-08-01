package com.trip.backend.infra.cache;

import java.util.Optional;
import java.util.concurrent.TimeUnit;

/**
 * 缓存后端抽象接口
 * @param <T> 缓存值类型
 */
public interface CacheBackend<T> {

    /**
     * 写入缓存
     */
    void put(String key, T value);

    /**
     * 写入缓存（带 TTL）
     */
    void put(String key, T value, long ttl, TimeUnit unit);

    /**
     * 读取缓存
     */
    Optional<T> get(String key);

    /**
     * 删除缓存
     */
    void delete(String key);

    /**
     * 清空所有缓存
     */
    void clear();

    /**
     * 检查后端是否可用
     */
    boolean isAvailable();
}
