package com.trip.backend.service.agent;

/**
 * Planner Agent（对应 Python agents/planner_agent.py）。
 *
 * 读 ResearchBundle，生成行程 JSON 字符串。
 * feedback 非空时表示带 review 意见重跑。
 */
public interface PlannerAgent {

    /** 输入。 */
    record Input(
        ResearchBundle bundle,
        String city,
        int days,
        int budget,
        String feedback,
        int attempt,
        String userMessage
    ) {
        public static Input first(ResearchBundle bundle, String city, int days, int budget, String userMessage) {
            return new Input(bundle, city, days, budget, "", 0, userMessage);
        }

        public Input withFeedback(String fb, int attemptNum) {
            return new Input(bundle, city, days, budget, fb, attemptNum, userMessage);
        }
    }

    /** 输出。 */
    record Output(String rawJson, String error) {
        public static Output ok(String json) {
            return new Output(json, null);
        }
        public static Output fail(String err) {
            return new Output(null, err);
        }
    }

    Output run(Input input);
}
