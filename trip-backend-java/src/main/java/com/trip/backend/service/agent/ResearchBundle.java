package com.trip.backend.service.agent;

import java.util.Set;

/**
 * Research 阶段产物（对应 Python schemas.ResearchBundle）。
 *
 * 候选池：ResearchAgent 并行调 5 工具后收集的可用景点名集合，
 * 供 review 做封闭世界校验（Planner 只能从池里挑 spot）。
 */
public record ResearchBundle(
    Set<String> spotNames,
    String attractions,
    String food,
    String hotels,
    String weather,
    String distance
) {
    public static ResearchBundle empty() {
        return new ResearchBundle(Set.of(), "", "", "", "", "");
    }

    /** 候选池全部景点名（review 封闭世界校验用）。 */
    public Set<String> allSpotNames() {
        return spotNames == null ? Set.of() : spotNames;
    }
}
