"""将文本层原始数据分块 + 计算可信度 + 写入 MySQL + embed + 写入 Chroma.

入：data/wiki_raw/{city}.json（fetch_wiki.py 产出）
出：spot_docs 表（MySQL）+ spot_docs 集合（Chroma）

设计要点（见 docs/rag-data-sources-and-credibility.md §6 / §7）：
- 分块：按 == 二级标题 == 切分；无标题则按句滑动窗口（300 字 / 重叠 60）。
  注：fetch_wiki.py 已请求 exsectionformat=wiki，回的 extract 含 == 标题 ==，
  故 chunk_text 的 == 分支已生效——长文按「引言/历史/景点特色…」等小节切成带标题
  的语义块（小节内仍超 300 字则滑窗），避免跨小节上下文串味。早期无 == 的 extract
  仍走滑窗兜底。300 字上限是为规避 BGE-small-zh-v1.5 的 512 token 上限（中文约
  1 字≈1 token，400 字会逼近/超出上限导致尾部被嵌入模型静默截断）。
- 可信度：compute_credibility(source_type="wiki") 写入时算好（5 维）。
- 双写：MySQL(spot_docs) 为权威源；Chroma(spot_docs) 为向量召回源。
- 降级：Chroma / embedding 不可用时仍写 MySQL（日志告警），不阻断 ETL。
- 幂等：写入前按 (spot_id, source_type) 删除旧块，避免重复累积。

用法：
    python scripts/ingest_spot_docs.py                  # 全量 wiki_raw
    python scripts/ingest_spot_docs.py --city 北京 --limit 5
    python scripts/ingest_spot_docs.py --source-type wiki --input-dir data/wiki_raw
"""

import argparse
import asyncio
import json
import os
import re
import uuid
from typing import List, Dict, Any, Optional

from sqlalchemy import select, delete

from src.config.database import async_session
# 全量模型导入：确保 SQLAlchemy 配置 mapper 时能解析所有关系
# （例如 User -> TokenUsageLog），否则首次建 session 会抛 InvalidRequestError。
import src.models.user  # noqa: F401
import src.models.conversation  # noqa: F401
import src.models.message  # noqa: F401
import src.models.trip  # noqa: F401
import src.models.spot  # noqa: F401
import src.models.spot_doc  # noqa: F401
import src.models.password_reset  # noqa: F401
import src.models.role  # noqa: F401
import src.models.feedback  # noqa: F401
import src.models.agent_step  # noqa: F401
import src.models.token_usage_log  # noqa: F401
from src.models.spot import Spot
from src.models.spot_doc import SpotDoc
from src.services.rag.credibility import compute_credibility
# 复用 fetch_wiki 的严格相关性判定，作为摄取前的防御性过滤：
# 仅把与景点真正相关的维基条目写入 spot_docs，避免错配内容（品牌POI错挂人物页 /
# 通用概念页错挂具体城市 POI）进入检索库，即使 wiki_raw 源数据含历史脏数据也能拦截。
from fetch_wiki import _is_relevant  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIKI_RAW_DIR = os.path.join(ROOT, "data", "wiki_raw")
SOURCE_NAME = {"wiki": "维基百科", "wikidata": "Wikidata", "gaode_detail": "高德 POI 详情"}


def _sliding_window(text: str, max_chars: int = 300, overlap: int = 60) -> List[str]:
    """按标点切句，滑动窗口拼接（窗口 max_chars，重叠 overlap）。"""
    sentences = re.split(r"(?<=[。！？!?；;\n])", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    chunks, cur = [], ""
    for s in sentences:
        if len(cur) + len(s) <= max_chars:
            cur += s
        else:
            if cur:
                chunks.append(cur)
            # 新窗口保留重叠
            if len(s) > max_chars:
                cur = s[:max_chars]
            else:
                cur = (cur[-overlap:] + s) if cur else s
    if cur:
        chunks.append(cur)
    return chunks


def chunk_text(text: str, max_chars: int = 300, overlap: int = 60) -> List[Dict[str, str]]:
    """把维基 extract 按 == 标题 == 切成带标题的块（段上限 max_chars 字）；无标题则句窗。

    max_chars 默认 300，刻意低于 BGE-small-zh-v1.5 的 512 token 上限，
    避免长块在嵌入时被静默截断。
    """
    lines = text.split("\n")
    sections: List[Dict[str, str]] = []
    heading, body = "", []
    for line in lines:
        m = re.match(r"^={2,}\s*(.+?)\s*={2,}$", line)
        if m:
            if heading or body:
                sections.append({"heading": heading, "body": "\n".join(body).strip()})
            heading, body = m.group(1).strip(), []
        else:
            body.append(line)
    if heading or body:
        sections.append({"heading": heading, "body": "\n".join(body).strip()})

    chunks: List[Dict[str, str]] = []
    for sec in sections:
        body_text = sec["body"]
        if not body_text:
            continue
        title = sec["heading"]
        full = (title + "\n" + body_text) if title else body_text
        if len(full) <= max_chars:
            if len(full) >= 30:
                chunks.append({"title": title, "content": full})
        else:
            for piece in _sliding_window(body_text, max_chars, overlap):
                chunks.append({"title": title, "content": (title + "\n" if title else "") + piece})
    return chunks


async def _map_spot_ids(session, city: str, names: List[str]) -> Dict[str, int]:
    """按 (name, city) 映射 spots.id（消歧双键）."""
    if not names:
        return {}
    result = await session.execute(
        select(Spot.id, Spot.name).where(Spot.city == city, Spot.name.in_(names))
    )
    return {row[1]: row[0] for row in result.all()}


async def ingest_city(
    session,
    city: str,
    raw_docs: List[Dict[str, Any]],
    source_type: str,
    limit: Optional[int],
) -> int:
    targets = raw_docs[:limit] if limit else raw_docs
    # 防御性过滤：只摄取与景点相关的维基条目，拦截错配/通用概念脏数据
    filtered = []
    for d in targets:
        if _is_relevant(d.get("spot_name", ""), city, d.get("title", ""), d.get("extract", "")):
            filtered.append(d)
        else:
            print(f"    [skip] 相关性不通过，跳过: {d.get('spot_name')} @ {city} (title={d.get('title')!r})")
    targets = filtered
    if not targets:
        return 0
    names = [d["spot_name"] for d in targets]
    id_map = await _map_spot_ids(session, city, names)

    docs_to_write: List[SpotDoc] = []

    for d in targets:
        spot_id = id_map.get(d["spot_name"])
        if not spot_id:
            print(f"    [skip] 未匹配到 spot: {d['spot_name']} @ {city}")
            continue
        chunks = chunk_text(d.get("extract", ""))
        evidence_density = min(1.0, len(chunks) / 10.0)
        for idx, ch in enumerate(chunks):
            cred = compute_credibility(
                source_type,
                evidence_density=evidence_density,
                published_at=None,
            )
            doc = SpotDoc(
                spot_id=spot_id,
                source_type=source_type,
                source_name=SOURCE_NAME.get(source_type, source_type),
                source_url=d.get("source_url"),
                title=ch["title"][:200],
                content=ch["content"],
                chunk_index=idx,
                authority_score=cred["authority_score"],
                freshness_score=cred["freshness_score"],
                agreement_score=cred["agreement_score"],
                citation_count=cred["citation_count"],
                evidence_density=cred["evidence_density"],
                credibility_score=cred["credibility_score"],
            )
            docs_to_write.append(doc)

    if not docs_to_write:
        return 0

    # 幂等：先删该城市这批 spot 的旧 wiki 块
    spot_ids = list({d.spot_id for d in docs_to_write})
    await session.execute(
        delete(SpotDoc).where(
            SpotDoc.spot_id.in_(spot_ids), SpotDoc.source_type == source_type
        )
    )
    session.add_all(docs_to_write)
    await session.commit()
    print(f"    MySQL 写入 {len(docs_to_write)} 块（{city}，{source_type}）")

    # 异步计算 embedding 写入 PG（降级友好）
    if docs_to_write:
        try:
            from src.services.rag.embeddings import embed_documents_async
            from sqlalchemy import update as sa_update

            texts = [d.content for d in docs_to_write]
            embeddings = await embed_documents_async(texts)
            for doc, emb in zip(docs_to_write, embeddings):
                await session.execute(
                    sa_update(SpotDoc)
                    .where(SpotDoc.id == doc.id)
                    .values(embedding=emb)
                )
            await session.commit()
            print(f"    pgvector 写入 {len(docs_to_write)} 向量")
        except Exception as e:
            print(f"    [warn] embedding 计算跳过（PG 文本已落库）: {e}")
    return len(docs_to_write)


async def main_async(args):
    if not os.path.isdir(args.input_dir):
        print(f"输入目录不存在: {args.input_dir}")
        return
    files = sorted(f for f in os.listdir(args.input_dir) if f.endswith(".json"))
    if args.city:
        files = [f for f in files if f[:-5] == args.city]
    total = 0
    async with async_session() as session:
        for cf in files:
            city = cf[:-5]
            with open(os.path.join(args.input_dir, cf), "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            print(f"摄取 {city}（{len(raw)} 条原始）...")
            n = await ingest_city(session, city, raw, args.source_type, args.limit)
            total += n
    print(f"完成：共写入 {total} 个文本块到 spot_docs")


def main():
    p = argparse.ArgumentParser(description="摄取文本层数据到 spot_docs")
    p.add_argument("--city", help="只处理指定城市")
    p.add_argument("--limit", type=int, help="每城最多 N 条原始（抽样）")
    p.add_argument("--source-type", default="wiki", help="source_type")
    p.add_argument("--input-dir", default=WIKI_RAW_DIR, help="原始数据目录")
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
