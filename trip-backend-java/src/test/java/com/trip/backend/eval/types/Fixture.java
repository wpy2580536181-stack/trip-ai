package com.trip.backend.eval.types;

import java.util.List;

/**
 * 完整 Fixture
 */
public class Fixture {
    private String id;
    private String description;
    private List<String> tags = List.of();
    private FixtureInput input;
    private FixtureExpected expected;
    private List<String> evaluators = List.of();

    public Fixture() {
    }

    public Fixture(String id, String description, List<String> tags, FixtureInput input, FixtureExpected expected, List<String> evaluators) {
        this.id = id;
        this.description = description;
        this.tags = tags;
        this.input = input;
        this.expected = expected;
        this.evaluators = evaluators;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public FixtureInput getInput() {
        return input;
    }

    public void setInput(FixtureInput input) {
        this.input = input;
    }

    public FixtureExpected getExpected() {
        return expected;
    }

    public void setExpected(FixtureExpected expected) {
        this.expected = expected;
    }

    public List<String> getEvaluators() {
        return evaluators;
    }

    public void setEvaluators(List<String> evaluators) {
        this.evaluators = evaluators;
    }
}
