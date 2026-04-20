"""商户搜索条件的 typed schema。

schema 只作为 submit_shop_search_criteria 工具的参数类型出现——LLM 在 tool-call
阶段看到 JSON Schema（含字段名、enum），但 instruction（prompt）层不再出现
这些字面量，避免泄漏到用户可见回复。

每个 Field 的 description 写的是抽取规则，不是候选值列表。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SortBy = Literal["distance", "rating", "tradingCount"]


class ShopSearchLeafParams(BaseModel):
    """LEAF.params 的可用字段。

    每个字段都只抽用户原话里明确说过的词；未提及的字段直接省略（不要传空串/None）。
    字段 description 是抽取规则，不是候选值；用户没说就不要照描述回填。
    """

    model_config = ConfigDict(extra="forbid")

    shop_type: str | None = Field(
        default=None,
        description="用户原话里对商户类型的描述，原样传。用户没说不填。",
    )
    shop_name: str | None = Field(
        default=None,
        description="用户原话里提到的具体商户名称，原样传。用户没说不填。",
    )
    location_text: str | None = Field(
        default=None,
        description=(
            "用户原话里的位置描述，任何粒度不拆、不猜。"
            "用户说'附近/这边'不算明确位置——那种情况下不要填本字段，"
            "改用 use_current_location。"
        ),
    )
    use_current_location: bool | None = Field(
        default=None,
        description="用户说'附近/这边/当前位置'之类要用当前定位时填 true；否则不填。",
    )
    min_rating: float | None = Field(
        default=None,
        description="用户明确给出的最低评分（1-5 数字）。用户没给具体数字不填。",
    )
    has_activity: bool | None = Field(
        default=None,
        description="用户明确说要有优惠活动时填 true；否则不填。",
    )
    project_keywords: list[str] | None = Field(
        default=None,
        description="用户原话里对养车服务的描述（如项目名），原样传。用户没说不填。",
    )
    equipment_keywords: list[str] | None = Field(
        default=None,
        description="用户原话里对设备的描述，原样传。用户没说不填。",
    )
    radius: int | None = Field(
        default=None,
        description=(
            "搜索半径，单位米。只有用户明说距离数字才填"
            "（'3公里内'→3000）。'附近'不算明确距离。"
        ),
    )
    fuzzy_keywords: list[str] | None = Field(
        default=None,
        description=(
            "用户原话里对商户的其他要求描述（营业时间、价格偏好之类），原样传。"
            "不放位置/商户/项目名等已有字段能接的词。用户没说不填。"
        ),
    )


class ShopSearchQuery(BaseModel):
    """查询树节点。LEAF=叶子条件；AND=全部命中；OR=任一命中。"""

    model_config = ConfigDict(extra="forbid")

    op: Literal["LEAF", "AND", "OR"] = Field(
        description="节点类型。LEAF 用 params；AND/OR 用 children。",
    )
    params: ShopSearchLeafParams | None = Field(
        default=None,
        description="仅 op=LEAF 时使用。",
    )
    children: list["ShopSearchQuery"] | None = Field(
        default=None,
        description="仅 op=AND 或 op=OR 时使用。",
    )


class ShopSearchInfo(BaseModel):
    """找店条件整包。query 必填。"""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )

    order_by: SortBy | None = Field(
        default=None,
        alias="orderBy",
        description=(
            "排序偏好。仅用户明确表达排序意图时才填。"
            "映射：用户说'离近的优先'→distance；'评分高的优先'→rating；"
            "'人气/交易量旺的优先'→tradingCount。"
            "禁止在对用户的回复里出现这三个英文字母。"
        ),
    )
    limit: int | None = Field(
        default=None,
        description="返回数量上限。用户没说不填。",
    )
    query: ShopSearchQuery = Field(
        description="查询树。至少组得出一个 LEAF 才调工具。",
    )
