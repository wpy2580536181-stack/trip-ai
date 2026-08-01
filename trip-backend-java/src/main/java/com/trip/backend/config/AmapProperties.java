package com.trip.backend.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 高德配置
 */
@Component
@ConfigurationProperties(prefix = "amap")
public class AmapProperties {

    private String mapsApiKey = "";
    private String mcpServerPath = "npx";

    // Getters/Setters
    public String getMapsApiKey() {
        return mapsApiKey;
    }

    public void setMapsApiKey(String mapsApiKey) {
        this.mapsApiKey = mapsApiKey;
    }

    public String getMcpServerPath() {
        return mcpServerPath;
    }

    public void setMcpServerPath(String mcpServerPath) {
        this.mcpServerPath = mcpServerPath;
    }
}
