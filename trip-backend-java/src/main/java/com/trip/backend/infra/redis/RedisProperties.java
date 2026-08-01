package com.trip.backend.infra.redis;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Redis 配置属性
 */
@ConfigurationProperties(prefix = "spring.data.redis")
public class RedisProperties {

    private String host = "localhost";
    private int port = 6379;
    private String password = "";
    private int database = 0;

    // Getters/Setters
    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    public int getDatabase() {
        return database;
    }

    public void setDatabase(int database) {
        this.database = database;
    }
}
