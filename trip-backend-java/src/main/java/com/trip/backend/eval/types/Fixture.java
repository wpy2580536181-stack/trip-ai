package com.trip.backend.eval.types;

import java.util.List;
import java.util.Map;

/**
 * Fixture: 测试用例
 */
public class Fixture {
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
    public Map<String, Object> preferences;
    public List<Map<String, Object>> history;
}

/**
 * FixtureExpected
 */
class FixtureExpected {
    public String city = "";
    public List<String> spotNames;
    public List<String> mustContainKeywords;
    public List<String> mustNotContainKeywords;
    public String keywordMatchMode = "all";
}
