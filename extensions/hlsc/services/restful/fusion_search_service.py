"""融合词库检索服务 — 精确匹配 + 模糊匹配 + RAG 语义检索。

调用 datamanager /otherlexiconquery/fusionSearch 接口，
根据关键词在指定词库（商户类型、设备、商户名、活动等）中检索匹配项。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from agent_sdk.logging import log_http_request, log_http_response

DATA_MANAGER_URL: str = os.getenv("DATA_MANAGER_URL", "")

# 可检索的词库名称
DOC_DISCOUNT_TYPE: str = "discountType"
DOC_COMMERCIAL_TYPE: str = "commercial_type"
DOC_EQUIPMENT: str = "equipment"
DOC_COMMERCIAL: str = "commercial"
DOC_COMMERCIAL_ACTIVITY: str = "commercial_activity"


# ============================================================
# 数据结构
# ============================================================


@dataclass
class MatchedItem:
    """单条匹配结果"""

    doc_name: str = ""
    source_id: str = ""
    title: str = ""
    content: str = ""
    keyword: str = ""
    similarity: float = 0.0


@dataclass
class FusionSearchResult:
    """fusionSearch 完整返回"""

    exact_matched: list[MatchedItem] = field(default_factory=list)
    fuzzy_matched: list[MatchedItem] = field(default_factory=list)
    rag_matched: list[MatchedItem] = field(default_factory=list)

    # ---- 便捷方法 ----

    def all_items(self) -> list[MatchedItem]:
        """返回全部匹配项（精确 + 模糊 + RAG），已去重。"""
        seen: set[tuple[str, str]] = set()
        result: list[MatchedItem] = []
        for item in self.exact_matched + self.fuzzy_matched + self.rag_matched:
            key: tuple[str, str] = (item.doc_name, item.source_id)
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    def get_by_doc(self, doc_name: str) -> list[MatchedItem]:
        """按词库名过滤全部匹配项。"""
        return [item for item in self.all_items() if item.doc_name == doc_name]

    def get_source_ids(self, doc_name: str) -> list[int]:
        """获取指定词库匹配的 source_id 列表（int）。"""
        ids: list[int] = []
        for item in self.get_by_doc(doc_name):
            if item.source_id:
                try:
                    ids.append(int(item.source_id))
                except ValueError:
                    pass
        return ids

    def get_titles(self, doc_name: str | None = None) -> list[str]:
        """获取匹配的 title 列表（去重、去空）。doc_name 为 None 时不过滤。"""
        items: list[MatchedItem] = self.get_by_doc(doc_name) if doc_name else self.all_items()
        seen: set[str] = set()
        titles: list[str] = []
        for item in items:
            if item.title and item.title not in seen:
                seen.add(item.title)
                titles.append(item.title)
        return titles

    def get_titles_by_keyword(self, doc_name: str | None = None) -> dict[str, list[str]]:
        """按 keyword 分组获取 title 列表（去重、去空）。doc_name 为 None 时不过滤。

        返回 {keyword: [title1, title2, ...]}
        """
        items: list[MatchedItem] = self.get_by_doc(doc_name) if doc_name else self.all_items()
        groups: dict[str, list[str]] = {}
        seen: dict[str, set[str]] = {}
        for item in items:
            if not item.keyword or not item.title:
                continue
            if item.keyword not in groups:
                groups[item.keyword] = []
                seen[item.keyword] = set()
            if item.title not in seen[item.keyword]:
                seen[item.keyword].add(item.title)
                groups[item.keyword].append(item.title)
        return groups


# ============================================================
# 解析
# ============================================================


def _parse_matched_list(raw_list: list[dict] | None) -> list[MatchedItem]:
    """解析 exact_matched / fuzzy_matched 列表。"""
    if not raw_list:
        return []
    items: list[MatchedItem] = []
    for entry in raw_list:
        row: dict = entry.get("row_info", {})
        items.append(MatchedItem(
            doc_name=row.get("doc_name", ""),
            source_id=str(row.get("source_id", "")),
            title=row.get("title", ""),
            content=row.get("content", ""),
            keyword=entry.get("keyword", ""),
        ))
    return items


def _parse_rag_list(raw_list: list[dict] | None) -> list[MatchedItem]:
    """解析 rag_matched 列表（嵌套 candidates）。"""
    if not raw_list:
        return []
    items: list[MatchedItem] = []
    for group in raw_list:
        keyword: str = group.get("keyword", "")
        for candidate in group.get("candidates", []):
            row: dict = candidate.get("row_info", {})
            items.append(MatchedItem(
                doc_name=row.get("doc_name", ""),
                source_id=str(row.get("source_id", "")),
                title=row.get("title", ""),
                content=row.get("content", ""),
                keyword=keyword,
                similarity=candidate.get("similarity", 0.0),
            ))
    return items


def _parse_result(raw: dict) -> FusionSearchResult:
    """将接口 result 解析为 FusionSearchResult。"""
    return FusionSearchResult(
        exact_matched=_parse_matched_list(raw.get("exact_matched")),
        fuzzy_matched=_parse_matched_list(raw.get("fuzzy_matched")),
        rag_matched=_parse_rag_list(raw.get("rag_matched")),
    )


# ============================================================
# 服务实现
# ============================================================


class FusionSearchService:
    """融合词库检索服务"""

    async def search(
        self,
        keywords: list[str],
        doc_names: list[str],
        top_k: int = 10,
        similarity_threshold: float = 0.3,
        vector_similarity_weight: float = 0.3,
        metadata_filters: dict[str, list[int]] | None = None,
        session_id: str = "",
        request_id: str = "",
    ) -> FusionSearchResult:
        """根据关键词在指定词库中检索匹配项。

        Args:
            keywords: 搜索关键词列表
            doc_names: 要检索的词库名称列表
            top_k: 每个关键词返回的最大匹配数
            similarity_threshold: RAG 相似度阈值
            vector_similarity_weight: 向量相似度权重
            metadata_filters: 元数据过滤，如 {"keywordType": [1,2,3]}

        Raises:
            RuntimeError: DATA_MANAGER_URL 未配置或 API 返回错误状态
        """
        if not DATA_MANAGER_URL:
            raise RuntimeError("DATA_MANAGER_URL 未配置")

        url: str = f"{DATA_MANAGER_URL}/service_ai_datamanager/otherlexiconquery/fusionSearch"
        payload: dict = {
            "keywords": keywords,
            "doc_names": doc_names,
            "top_k": top_k,
            "similarity_threshold": similarity_threshold,
            "vector_similarity_weight": vector_similarity_weight,
        }
        if metadata_filters is not None:
            payload["metadata_filters"] = metadata_filters
        log_http_request(url, "POST", session_id, request_id, payload)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response: httpx.Response = await client.post(url, json=payload)
            response.raise_for_status()
            data: dict = response.json()
            log_http_response(response.status_code, session_id, request_id, data)

        if data.get("status") != 0:
            raise RuntimeError(f"融合检索失败: {data.get('message', '未知错误')}")

        raw_result = data.get("result", {})
        if not isinstance(raw_result, dict):
            return FusionSearchResult()
        return _parse_result(raw_result)


fusion_search_service: FusionSearchService = FusionSearchService()
