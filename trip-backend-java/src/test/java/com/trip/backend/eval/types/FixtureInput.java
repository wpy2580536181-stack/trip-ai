package com.trip.backend.eval.types;

import java.util.List;
import java.util.Map;

/**
 * Fixture input 节
 */
public class FixtureInput {
    private String message = "";
    private Map<String, Object> preferences = Map.of();
    private List<Map<String, Object>> history = List.of();

    public FixtureInput() {
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public Map<String, Object> getPreferences() {
        return preferences;
    }

    public void setPreferences(Map<String, Object> preferences) {
        this.preferences = preferences;
    }

    public List<Map<String, Object>> getHistory() {
        return history;
    }

    public void setHistory(List<Map<String, Object>> history) {
        this.history = history;
    }
}
