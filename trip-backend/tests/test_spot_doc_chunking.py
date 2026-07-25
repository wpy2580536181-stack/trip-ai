"""Tests for spot_docs chunking (scripts/ingest_spot_docs.py chunk_text / _sliding_window).

验证 fetch_wiki.py 加 exsectionformat=wiki 后，维基 extract 含 == 标题 ==，
chunk_text 的按段切分分支应生效（此前为死代码，全走滑窗）。
"""
import os
import sys

# ingest_spot_docs 用 `from fetch_wiki import _is_relevant` 的裸导入，需把 scripts/ 加入 path
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from ingest_spot_docs import chunk_text, _sliding_window  # noqa: E402


class TestChunkTextSections:
    """验证 chunk_text 的 == 标题 == 分段分支（fetch 加 exsectionformat=wiki 后生效）。"""

    def test_splits_on_wiki_headings_into_titled_chunks(self):
        text = (
            # 引言（无标题，需 >30 字才保留）
            "布达拉宫是西藏拉萨著名的宫堡式建筑群，位于红山之上，是藏传佛教的圣地与象征。\n"
            "== 历史 ==\n"
            "布达拉宫始建于公元7世纪，由松赞干布兴建，后经历代扩建形成今日规模。"
            "1645年五世达赖喇嘛重建白宫，1690年兴建红宫，1994年列入世界文化遗产。\n"
            "== 建筑特色 ==\n"
            "布达拉宫依山而建，高117米，外观13层，内部有宫殿、灵塔、佛殿、经堂等。"
            "红宫居中供奉历代达赖灵塔，白宫为政务与生活区，宫中珍宝无数。"
        )
        chunks = chunk_text(text, max_chars=300, overlap=60)
        # 引言(无标题) + 历史 + 建筑特色 = 3 块
        assert len(chunks) == 3
        titles = [c["title"] for c in chunks]
        assert titles[0] == ""  # 引言无标题
        assert titles[1] == "历史"
        assert titles[2] == "建筑特色"
        # 带标题块的正文应含该段内容，且标题作为上下文前置
        assert "松赞干布" in chunks[1]["content"]
        assert "依山而建" in chunks[2]["content"]

    def test_subsection_heading_three_equals_is_captured(self):
        text = (
            "== 概述 ==\n这是概述段落，描述景点总体情况，长度需要超过三十个字符才能被保留。\n"
            "=== 子项 ===\n这是子项段落，进一步展开细节，同样需要足够长度以通过最小块过滤。\n"
        )
        chunks = chunk_text(text, max_chars=300, overlap=60)
        titles = [c["title"] for c in chunks]
        assert "概述" in titles
        assert "子项" in titles

    def test_long_section_falls_back_to_sliding_window_with_title_prefix(self):
        # 单段超 max_chars，应滑窗切分，且每块保留标题前缀
        long_body = "。".join([f"历史细节{i}描述内容较长一些" for i in range(40)]) + "。"
        text = f"== 历史 ==\n{long_body}\n"
        chunks = chunk_text(text, max_chars=120, overlap=30)
        assert len(chunks) >= 2
        for c in chunks:
            assert c["title"] == "历史"
            assert c["content"].startswith("历史\n")

    def test_plain_text_without_headings_uses_sliding_window(self):
        text = "。".join([f"普通句子{i}内容稍长一点" for i in range(20)]) + "。"
        chunks = chunk_text(text, max_chars=120, overlap=30)
        assert len(chunks) >= 1
        for c in chunks:
            assert c["title"] == ""
            assert "==" not in c["content"]


class TestSlidingWindow:
    def test_basic_windowing_respects_max_chars(self):
        text = "。".join([f"句{i}内容稍长一些" for i in range(30)]) + "。"
        chunks = _sliding_window(text, max_chars=50, overlap=10)
        assert len(chunks) >= 2
        for c in chunks:
            assert len(c) <= 50

    def test_overlap_preserved_between_windows(self):
        # 重叠出现在相邻窗口之间：后块以「前块尾部 overlap 字」开头。
        # 用若干 <= max_chars 的短句，才能触发 cur[-overlap:] + 新句的重叠拼接。
        text = (
            "甲甲甲甲甲甲甲甲甲甲。"
            "乙乙乙乙乙乙乙乙乙乙。"
            "丙丙丙丙丙丙丙丙丙丙。"
        )
        chunks = _sliding_window(text, max_chars=20, overlap=5)
        assert len(chunks) >= 2
        # 第二块应以第一块尾部 5 字开头（重叠）
        assert chunks[1].startswith(chunks[0][-5:])
