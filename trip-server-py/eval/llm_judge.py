"""
LLM-as-Judge 模块。

封装 DeepSeek API 调用，提供 Faithfulness、Answer Relevancy
等指标的评分能力。不依赖 langchain，使用 httpx 直接调用 API。

环境变量:
  DEEPSEEK_API_KEY: DeepSeek API key（必需）
  DEEPSEEK_BASE_URL: API 地址（默认 https://api.deepseek.com/v1）
  LLM_JUDGE_MODEL: 模型名（默认 deepseek-chat）
"""

import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
_DEFAULT_MODEL = "deepseek-chat"


class LLMJudgeError(Exception):
    """LLM Judge 调用异常"""


def _get_api_key() -> Optional[str]:
    """获取 API key（优先环境变量，回退到 .env 文件）"""
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_JUDGE_API_KEY")
    if key:
        return key
    # 尝试从 .env 文件读取
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    return None


def _get_judge_config() -> dict:
    """获取 Judge 配置"""
    return {
        "api_key": _get_api_key() or "",
        "base_url": os.environ.get("DEEPSEEK_BASE_URL", _DEFAULT_BASE_URL),
        "model": os.environ.get("LLM_JUDGE_MODEL", _DEFAULT_MODEL),
    }


def _call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    timeout: int = 30,
) -> str:
    """调用 DeepSeek API 执行评判。

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        temperature: 温度参数（评判场景固定为 0）
        max_tokens: 最大输出 token
        timeout: 超时秒数

    Returns:
        LLM 返回的文本内容

    Raises:
        LLMJudgeError: API 调用失败或未配置 API key
    """
    cfg = _get_judge_config()
    if not cfg["api_key"]:
        raise LLMJudgeError(
            "LLM Judge 未配置 API key。请设置环境变量 DEEPSEEK_API_KEY "
            "或在 .env 文件中配置 DEEPSEEK_API_KEY"
        )

    url = f"{cfg['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    body = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        resp = httpx.post(url, headers=headers, json=body, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return content.strip()
    except httpx.HTTPError as e:
        raise LLMJudgeError(f"LLM API 调用失败: {e}")
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise LLMJudgeError(f"LLM 响应解析失败: {e}, body={resp.text[:200]}")


def _parse_json_from_llm(text: str) -> dict:
    """从 LLM 输出中提取 JSON 对象。"""
    # 尝试直接解析
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # 查找 ```json ... ``` 代码块
    import re
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 查找最外层 { ... }
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = -1
    return {}


# ──────────────────────────────────────────────
# 评分函数
# ──────────────────────────────────────────────


def score_faithfulness(answer: str, contexts: list[str]) -> dict:
    """计算 Faithfulness（忠实度）。

    将答案拆解为独立陈述，逐一判断是否在上下文中有依据。

    Returns:
        {"score": float, "claims": [...], "raw": str}
    """
    if not answer.strip():
        return {"score": 0.0, "claims": [], "raw": "空答案"}
    if not contexts:
        return {"score": 0.0, "claims": [], "raw": "无检索上下文"}

    contexts_text = "\n---\n".join(contexts)

    system_prompt = (
        "你是一个严谨的评估助手。你的任务是判断'回答'中的每个独立事实陈述"
        "是否在给定的'参考上下文'中有明确的依据。\n\n"
        "请按以下步骤操作：\n"
        "1. 将回答拆解为多个独立的事实陈述（每个陈述只包含一个事实）\n"
        "2. 逐一判断每个陈述能否在参考上下文中找到明确的依据\n"
        "3. 如果陈述是对上下文信息的合理概括或同义转述，也算有依据\n"
        "4. 如果陈述包含上下文里没有的信息，算无依据\n\n"
        "以 JSON 格式输出，不要包含其他内容：\n"
        '{"claims": [{"statement": "...", "supported": true/false, "evidence": "..."}]}'
    )

    user_prompt = f"参考上下文：\n{contexts_text}\n\n回答：\n{answer}"

    try:
        raw = _call_llm(system_prompt, user_prompt)
        parsed = _parse_json_from_llm(raw)
        claims = parsed.get("claims", [])
        if not claims:
            logger.warning("Faithfulness 未解析到 claims: %s", raw[:200])
            return {"score": 0.5, "claims": [], "raw": raw}

        supported = sum(1 for c in claims if c.get("supported", False))
        score = supported / len(claims) if claims else 0.0
        return {"score": round(score, 4), "claims": claims, "raw": raw}
    except LLMJudgeError as e:
        logger.warning("Faithfulness 评分失败: %s", e)
        return {"score": 0.0, "claims": [], "raw": str(e)}


def score_answer_relevancy(question: str, answer: str) -> dict:
    """计算 Answer Relevancy（答案相关性）。

    判断答案是否准确回应了用户的问题。

    Returns:
        {"score": float, "reason": str, "raw": str}
    """
    if not answer.strip():
        return {"score": 0.0, "reason": "空答案", "raw": ""}

    system_prompt = (
        "你是一个评估助手。请判断'回答'是否准确回应了'问题'。\n\n"
        "评分标准（1-5分）：\n"
        "1分：完全无关，答非所问\n"
        "2分：大部分内容与问题无关\n"
        "3分：部分相关，但没有完全回答问题\n"
        "4分：基本回答了问题，但有少量无关内容\n"
        "5分：精准并完整地回答了问题\n\n"
        "以 JSON 格式输出，不要包含其他内容：\n"
        '{"score": 5, "reason": "..."}'
    )

    user_prompt = f"问题：{question}\n回答：{answer}"

    try:
        raw = _call_llm(system_prompt, user_prompt)
        parsed = _parse_json_from_llm(raw)
        score_raw = parsed.get("score", 3)
        reason = parsed.get("reason", "")
        # 归一化到 0-1
        score = round(score_raw / 5.0, 4)
        return {"score": score, "reason": reason, "raw": raw}
    except LLMJudgeError as e:
        logger.warning("Answer Relevancy 评分失败: %s", e)
        return {"score": 0.0, "reason": str(e), "raw": ""}


def score_context_recall(contexts: list[str], ground_truth: str) -> dict:
    """计算 Context Recall（上下文召回率）。

    判断检索到的上下文是否覆盖了回答所需的所有关键信息。
    需要 ground_truth 作为理想答案参照。

    Returns:
        {"score": float, "covered": int, "total": int, "raw": str}
    """
    if not contexts:
        return {"score": 0.0, "covered": 0, "total": 0, "raw": "无检索上下文"}
    if not ground_truth.strip():
        return {"score": 0.0, "covered": 0, "total": 0, "raw": "无 ground truth"}

    contexts_text = "\n---\n".join(contexts)

    system_prompt = (
        "你是一个评估助手。请判断给定的'检索上下文'是否覆盖了"
        "'理想答案'中的关键信息。\n\n"
        "请将理想答案拆解为多个关键信息点，然后逐一判断每个信息点"
        "是否能在检索上下文中找到依据。\n\n"
        "以 JSON 格式输出：\n"
        '{"points": [{"info": "...", "covered": true/false}], '
        '"reason": "简要说明"}'
    )

    user_prompt = f"检索上下文：\n{contexts_text}\n\n理想答案：\n{ground_truth}"

    try:
        raw = _call_llm(system_prompt, user_prompt)
        parsed = _parse_json_from_llm(raw)
        points = parsed.get("points", [])
        if not points:
            return {"score": 0.5, "covered": 0, "total": 0, "raw": raw}

        covered = sum(1 for p in points if p.get("covered", False))
        total = len(points)
        score = covered / total if total > 0 else 0.0
        return {"score": round(score, 4), "covered": covered, "total": total, "raw": raw}
    except LLMJudgeError as e:
        logger.warning("Context Recall 评分失败: %s", e)
        return {"score": 0.0, "covered": 0, "total": 0, "raw": str(e)}


def score_context_precision(contexts: list[str], ground_truth: str) -> dict:
    """计算 Context Precision（上下文精确率）。

    判断检索结果中相关 chunk 的排序质量。
    需要 ground_truth 作为理想答案参照。

    Returns:
        {"score": float, "ranked_relevance": [...], "raw": str}
    """
    if not contexts:
        return {"score": 0.0, "ranked_relevance": [], "raw": "无检索上下文"}

    if len(contexts) <= 1:
        return {"score": 1.0, "ranked_relevance": [True], "raw": "仅一个上下文"}

    contexts_text = "\n---\n".join(contexts)

    system_prompt = (
        "你是一个评估助手。请判断每个'检索上下文'是否与'理想答案'描述的内容相关。\n"
        "按上下文给出的顺序逐一判断。\n\n"
        "以 JSON 格式输出：\n"
        '{"relevance": [true, false, true, ...], "reason": "..."}'
    )

    user_prompt = f"检索上下文列表：\n{contexts_text}\n\n理想答案：\n{ground_truth}"

    try:
        raw = _call_llm(system_prompt, user_prompt)
        parsed = _parse_json_from_llm(raw)
        relevance = parsed.get("relevance", [])
        if not relevance:
            return {"score": 0.5, "ranked_relevance": [], "raw": raw}

        # 计算 Precision@k 的平均值
        precision_sum = 0.0
        relevant_count = 0
        for k, rel in enumerate(relevance, 1):
            if rel:
                relevant_count += 1
                precision_sum += relevant_count / k

        score = precision_sum / relevant_count if relevant_count > 0 else 0.0
        return {
            "score": round(score, 4),
            "ranked_relevance": relevance,
            "raw": raw,
        }
    except LLMJudgeError as e:
        logger.warning("Context Precision 评分失败: %s", e)
        return {"score": 0.0, "ranked_relevance": [], "raw": str(e)}


def score_all(
    question: str,
    answer: str,
    contexts: Optional[list[str]] = None,
    ground_truth: Optional[str] = None,
) -> dict:
    """计算所有可用的 RAGAs 指标。

    Args:
        question: 用户问题
        answer: Agent 回答
        contexts: 检索到的上下文列表（可选）
        ground_truth: 理想答案（可选）

    Returns:
        包含所有计算结果的字典
    """
    results = {"answer_relevancy": score_answer_relevancy(question, answer)}

    if contexts:
        results["faithfulness"] = score_faithfulness(answer, contexts)
        if ground_truth:
            results["context_recall"] = score_context_recall(contexts, ground_truth)
            results["context_precision"] = score_context_precision(contexts, ground_truth)

    return results
