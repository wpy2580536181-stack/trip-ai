package com.trip.backend.eval.types;

import java.util.List;

/**
 * Agent 工具调用记录
 */
public class ToolCall {
    private String name;
    private Object args;
    private Object result;
    private String timestamp;

    public ToolCall() {
    }

    public ToolCall(String name, Object args, Object result, String timestamp) {
        this.name = name;
        this.args = args;
        this.result = result;
        this.timestamp = timestamp;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Object getArgs() {
        return args;
    }

    public void setArgs(Object args) {
        this.args = args;
    }

    public Object getResult() {
        return result;
    }

    public void setResult(Object result) {
        this.result = result;
    }

    public String getTimestamp() {
        return timestamp;
    }

    public void setTimestamp(String timestamp) {
        this.timestamp = timestamp;
    }
}
