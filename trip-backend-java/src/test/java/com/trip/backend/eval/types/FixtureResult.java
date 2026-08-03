package com.trip.backend.eval.types;

import java.util.Map;

/**
 * Fixture 整体执行结果
 */
public class FixtureResult {
    private String fixtureId;
    private String description;
    private String tags;
    private boolean passed;
    private AgentOutput agentOutput;
    private Map<String, EvalResult> evaluatorResults;
    private long durationMs = 0;
    private String error;

    public FixtureResult() {
    }

    public FixtureResult(String fixtureId, String description, String tags, boolean passed, AgentOutput agentOutput, Map<String, EvalResult> evaluatorResults, long durationMs, String error) {
        this.fixtureId = fixtureId;
        this.description = description;
        this.tags = tags;
        this.passed = passed;
        this.agentOutput = agentOutput;
        this.evaluatorResults = evaluatorResults;
        this.durationMs = durationMs;
        this.error = error;
    }

    public String getFixtureId() {
        return fixtureId;
    }

    public void setFixtureId(String fixtureId) {
        this.fixtureId = fixtureId;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public String getTags() {
        return tags;
    }

    public void setTags(String tags) {
        this.tags = tags;
    }

    public boolean isPassed() {
        return passed;
    }

    public void setPassed(boolean passed) {
        this.passed = passed;
    }

    public AgentOutput getAgentOutput() {
        return agentOutput;
    }

    public void setAgentOutput(AgentOutput agentOutput) {
        this.agentOutput = agentOutput;
    }

    public Map<String, EvalResult> getEvaluatorResults() {
        return evaluatorResults;
    }

    public void setEvaluatorResults(Map<String, EvalResult> evaluatorResults) {
        this.evaluatorResults = evaluatorResults;
    }

    public long getDurationMs() {
        return durationMs;
    }

    public void setDurationMs(long durationMs) {
        this.durationMs = durationMs;
    }

    public String getError() {
        return error;
    }

    public void setError(String error) {
        this.error = error;
    }
}
