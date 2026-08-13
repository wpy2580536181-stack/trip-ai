package com.trip.backend.eval.types;

import java.util.List;
import java.util.Map;

/**
 * AgentOutput
 */
class AgentOutput {
    public String text = "";
    public Map<String, Object> json;
    public List<ToolCall> toolCalls = List.of();
    public String error;
    public TokenUsage tokens = new TokenUsage();
    public long durationMs = 0;
    public Long conversationId = null;
}

/**
 * TokenUsage
 */
class TokenUsage {
    public int prompt = 0;
    public int completion = 0;
    public int total = 0;
    public int cached = 0;
}

/**
 * ToolCall
 */
class ToolCall {
    public String name;
    public Map<String, Object> args;
    public Object result;
    public String timestamp;
}

/**
 * EvalResult
 */
class EvalResult {
    public String name;
    public boolean passed;
    public String reason;
    public Map<String, Object> metadata;

    public EvalResult(String name, boolean passed) {
        this(name, passed, null);
    }

    public EvalResult(String name, boolean passed, String reason) {
        this.name = name;
        this.passed = passed;
        this.reason = reason;
        this.metadata = Map.of();
    }
}

/**
 * FixtureResult
 */
class FixtureResult {
    public String fixtureId;
    public String description;
    public boolean passed;
    public AgentOutput agentOutput;
    public List<EvalResult> evaluatorResults = List.of();
    public String error;
    public Map<String, Object> metadata;
}

/**
 * Fixture 测试用例
 */
class Fixture {
    public String id;
    public String description;
    public List<String> tags;
    public FixtureInput input;
    public FixtureExpected expected;
    public List<String> evaluators;
}

/**
 * FixtureInput
 */
class FixtureInput {
    public String message = "";
    public Map<String, Object> preferences = Map.of();
    public List<Map<String, Object>> history = List.of();
}

/**
 * FixtureExpected
 */
class FixtureExpected {
    public String city = "";
    public List<String> spotNames = List.of();
    public List<PoiMatch> mustContainPois = List.of();
    public List<String> mustContainKeywords = List.of();
    public List<String> mustNotContainKeywords = List.of();
    public int days = 0;
    public boolean jsonValid = false;
    public boolean isRecommendation = false;
    public boolean isDetailAnswer = false;
    public int maxActivitiesPerDay = 0;
    public List<ToolCallRule> toolCalls = List.of();
    public boolean activitiesHavePriceField = false;
    public boolean containsPriceNumber = false;
    public String groundTruth = "";
    public String keywordMatchMode = "all";
}

/**
 * PoiMatch
 */
class PoiMatch {
    public String name;
    public String nameContains;
    public String city;
    public String cityNearby;
}

/**
 * ToolCallRule
 */
class ToolCallRule {
    public String name;
    public int minCalls = 0;
    public int maxCalls = -1;
}
