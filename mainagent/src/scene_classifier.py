"""Scene classifier: before_agent_run_hook implementation."""

from __future__ import annotations

import json
from typing import Any, Literal

from openai import AsyncAzureOpenAI, AsyncOpenAI
from pydantic import BaseModel

from agent_sdk._agent.agent_message import AssistantMessage, UserMessage
from agent_sdk._agent.memory.file_memory_message_service import FileMemoryMessageService
from agent_sdk._agent.memory.sqlite_memory_message_service import SqliteMemoryMessageService
from agent_sdk._config.settings import get_inner_storage_backend
from agent_sdk.config import MemoryConfig
from src.config import ClassifyConfig

from src.hlsc_context import HlscRequestContext, SceneInfo

SceneType = Literal["chat", "clarify", "execute"]


class _SceneDecision(BaseModel):
    scene_type: SceneType
    confidence: float
    reasoning: str = ""


class SceneClassifier:
    """场景识别器：基于当前消息 + 历史进行分类。"""

    def __init__(self, config: ClassifyConfig | None = None) -> None:
        self._config = config or ClassifyConfig()

    async def classify(
        self,
        user_id: str,
        session_id: str,
        message: str,
        request_id: str,
    ) -> SceneInfo:
        if not self._config.enabled:
            return SceneInfo(scene_type="clarify", confidence=0.0, request_id=request_id)

        recent_dialogue = await self._load_recent_dialogue(user_id, session_id)

        decision = await self._classify_with_model(
            message=message,
            recent_dialogue=recent_dialogue,
        )

        return SceneInfo(
            scene_type=decision.scene_type,
            confidence=max(0.0, min(1.0, decision.confidence)),
            request_id=request_id,
        )

    async def _load_recent_dialogue(self, user_id: str, session_id: str) -> list[dict[str, str]]:
        history_limit = max(1, self._config.history_limit)

        mem_cfg = MemoryConfig()
        if mem_cfg.backend == "sqlite":
            svc = SqliteMemoryMessageService(mem_cfg.data_dir)
        else:
            svc = FileMemoryMessageService(get_inner_storage_backend())

        messages = await svc.load(user_id, session_id)

        # 仅保留 request_start/request_end 的语义消息（不做旧逻辑兼容）
        dialogue: list[dict[str, str]] = []
        for m in messages:
            if isinstance(m, UserMessage):
                if m.metadata.get("is_meta"):
                    continue
                phase = m.metadata.get("request_phase")
                if phase not in {"request_start", "request_end"}:
                    continue
                text = (m.content or "").strip()
                if text:
                    dialogue.append({"role": "user", "content": text})
            elif isinstance(m, AssistantMessage):
                phase = m.metadata.get("request_phase")
                if phase not in {"request_start", "request_end"}:
                    continue
                text = (m.content or "").strip()
                if text:
                    dialogue.append({"role": "assistant", "content": text})

        if len(dialogue) > history_limit:
            dialogue = dialogue[-history_limit:]
        return dialogue

    async def _classify_with_model(
        self,
        *,
        message: str,
        recent_dialogue: list[dict[str, str]],
    ) -> _SceneDecision | None:
        try:
            system_prompt = """# Role
你是一个专业的车主服务对话状态追踪器 (Dialogue State Tracker)。
你的任务是观察“车主”与“话痨”（AI助理）之间的最新一轮对话，并精准判定当前对话所属的业务阶段。

# State Definitions
你必须将当前对话严格归类为以下三种状态之一：

- chat（闲聊与养车服务需求挖掘 / Discovery）
  核心特征：车主在咨询宽泛的用车常识、表达模糊的需求（如“我想买车”或“车有点异响”），或进行非业务类的日常闲聊。
  触发条件：尚未明确具体要找哪家商户、什么具体项目服务、什么时间。

- clarify（预订方案与计划确定 / Planning）
  核心特征：AI 正在为车主进行查价、比价，提供具体的服务项目或商户选项，或正在协商预约的具体时间、门店和价格。
  触发条件：需求已明确，正在细化并锁定交易要素（Who, Where, When, How much, What），但尚未执行最终预订动作。

- execute（执行预订计划 / Execution & Follow-up）
  核心特征：车主已明确同意某个具体方案，AI 正在执行实质性的预订下单，或正在播报预约成功的确认信息。
  触发条件：确认达成一致，重点在于“动作执行”或“结果反馈”。

# Rules for State Transition
1. 聚焦最新意图：如果车主在 execute 阶段突然问“对了，新车磨合期要注意什么？”，状态必须立即切回 chat。以车主最新一句话的核心意图为最高优先级。
2. 混合状态处理：如果车主的话语同时包含两个阶段的特征（如“那就定这家吧，另外以后保养也在这里吗？”），以最靠后的业务推进阶段为准（此处应判为 execute）。

# Input Format
你将收到一个 JSON 对象，包含以下字段：
- current_message: 车主的最新发言
- recent_dialogue: 最近的对话历史（含车主和话痨的交替发言）

# Output Format
你必须仅输出一个严格 JSON 对象，不允许包含任何多余的解释文本或 Markdown 标记：
{"reasoning":"根据车主最新意图的简短思考","scene_type":"chat|clarify|execute","confidence":0.0~1.0}
"""
            payload = {
                "current_message": message,
                "recent_dialogue": recent_dialogue,
            }

            if self._config.provider == "azure":
                client = AsyncAzureOpenAI(
                    azure_endpoint=self._config.azure_endpoint,
                    api_key=self._config.azure_api_key,
                    api_version=self._config.azure_api_version,
                    max_retries=self._config.max_retries,
                )
                model = self._config.azure_deployment_name
            else:
                client = AsyncOpenAI(
                    api_key=self._config.api_key,
                    base_url=self._config.base_url or None,
                    max_retries=self._config.max_retries,
                )
                model = self._config.model_name

            if not model:
                return None

            resp = await client.chat.completions.create(
                model=model,
                temperature=self._config.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
            )
            content = (resp.choices[0].message.content or "").strip()
            if not content:
                return None
            data = json.loads(content)
            return _SceneDecision.model_validate(data)
        except Exception:
            return None

_CLASSIFIER = SceneClassifier()


async def before_agent_run_hook(
    user_id: str,
    session_id: str,
    deps: Any,
    message: str,
) -> None:
    """运行前场景钩子：写入 scene_info。"""
    request_id = getattr(deps, "request_id", "")
    ctx = getattr(deps, "request_context", None)

    # 同一 request_id 已判定过则直接复用
    existing: Any = None
    if isinstance(ctx, dict):
        existing = ctx.get("scene_info")
    elif ctx is not None:
        existing = getattr(ctx, "scene_info", None)

    if isinstance(existing, dict) and existing.get("request_id") == request_id:
        return
    if isinstance(existing, SceneInfo) and existing.request_id == request_id:
        return

    scene_info = await _CLASSIFIER.classify(
        user_id=user_id,
        session_id=session_id,
        message=message,
        request_id=request_id,
    )

    if isinstance(ctx, dict):
        ctx["scene_info"] = scene_info.model_dump()
        return
    if isinstance(ctx, HlscRequestContext):
        ctx.scene_info = scene_info
        return
    if ctx is None:
        deps.request_context = HlscRequestContext(scene_info=scene_info)
        return

    try:
        setattr(ctx, "scene_info", scene_info)
    except Exception:
        deps.request_context = HlscRequestContext(scene_info=scene_info)
