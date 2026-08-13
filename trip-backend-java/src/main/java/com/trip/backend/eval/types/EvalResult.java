package com.trip.backend.eval.types;

/**
 * EvalResult: Evaluator 执行结果
 */
public class EvalResult {
    public String name;
    public boolean passed;
    public String reason;

    public EvalResult(String name, boolean passed) {
        this(name, passed, null);
    }

    public EvalResult(String name, boolean passed, String reason) {
        this.name = name;
        this.passed = passed;
        this.reason = reason;
    }
}
