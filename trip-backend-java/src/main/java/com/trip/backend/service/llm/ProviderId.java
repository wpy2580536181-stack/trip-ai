package com.trip.backend.service.llm;

/**
 * Provider 枚举
 */
public enum ProviderId {
    DEEPSEEK("deepseek"),
    KIMI("kimi"),
    AGNESE("agnese");

    private final String value;

    ProviderId(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    public static ProviderId from(String value) {
        return switch (value.toLowerCase()) {
            case "deepseek" -> DEEPSEEK;
            case "kimi", "moonshot" -> KIMI;
            case "agnese", "agnes" -> AGNESE;
            default -> throw new IllegalArgumentException("Unknown provider: " + value);
        };
    }
}
