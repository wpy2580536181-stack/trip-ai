package com.trip.backend.service.agent.card;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 卡片事件结构约束（对应 Python chat 流后卡片校验）。
 *
 *  - info_text ≤ 1500 字
 *  - poi_list ≤ 10 条
 *  - commute_compare ≤ 5 条
 * 超限一律截断，保证 SSE 卡片结构合规。
 */
public final class CardEventBuilder {

    public static final int MAX_INFO_TEXT = 1500;
    public static final int MAX_POI_LIST = 10;
    public static final int MAX_COMMUTE_COMPARE = 5;

    private CardEventBuilder() {}

    /** 构造合规卡片（截断超长字段）。 */
    public static Map<String, Object> buildCard(String type, String infoText,
                                                List<?> poiList, List<?> commuteCompare) {
        return Map.of(
            "type", type,
            "info_text", truncate(infoText, MAX_INFO_TEXT),
            "poi_list", cap(poiList, MAX_POI_LIST),
            "commute_compare", cap(commuteCompare, MAX_COMMUTE_COMPARE)
        );
    }

    /** info_text 单字段截断（用于仅文本卡片）。 */
    public static String truncateInfoText(String text) {
        return truncate(text, MAX_INFO_TEXT);
    }

    static String truncate(String s, int max) {
        if (s == null) return "";
        return s.length() <= max ? s : s.substring(0, max);
    }

    @SuppressWarnings("unchecked")
    static List<Object> cap(List<?> list, int max) {
        if (list == null) return new ArrayList<>();
        return new ArrayList<>(list.size() <= max ? list : list.subList(0, max));
    }
}
