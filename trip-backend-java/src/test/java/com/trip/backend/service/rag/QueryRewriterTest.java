package com.trip.backend.service.rag;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * QueryRewriter 测试
 */
class QueryRewriterTest {

    private final QueryRewriter queryRewriter = new QueryRewriter();

    @Test
    void testExtractKeywords() {
        List<String> keywords = queryRewriter.extractKeywords("我想去北京故宫玩", 10);
        assertThat(keywords).containsExactly("北京", "故宫");
    }

    @Test
    void testRewriteQueryWithCity() {
        String rewritten = queryRewriter.rewriteQuery("我想去故宫玩", "北京");
        assertThat(rewritten).isEqualTo("北京 故宫 玩");
    }

    @Test
    void testRewriteQueryWithoutCity() {
        String rewritten = queryRewriter.rewriteQuery("北京故宫好玩吗");
        assertThat(rewritten).isEqualTo("北京故宫好玩吗");
    }

    @Test
    void testDetectCity() {
        assertThat(queryRewriter.detectCity("我想去北京玩")).isEqualTo("北京");
        assertThat(queryRewriter.detectCity("上海有什么好吃的")).isEqualTo("上海");
        assertThat(queryRewriter.detectCity("不知道去哪")).isNull();
    }

    @Test
    void testDetectIntent() {
        assertThat(queryRewriter.detectIntent("北京有什么好吃的")).isEqualTo("food");
        assertThat(queryRewriter.detectIntent("我想去故宫玩")).isEqualTo("scenic");
        assertThat(queryRewriter.detectIntent("推荐个酒店")).isEqualTo("hotel");
        assertThat(queryRewriter.detectIntent("怎么去机场")).isEqualTo("transport");
    }
}
