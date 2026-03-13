"""Agent：纯逻辑层，封装 agent loop + 所有核心服务

使用方式：
    from agent_sdk import Agent, StaticPromptLoader

    agent = Agent(
        prompt_loader=StaticPromptLoader("你是一个助手"),
        tools={"ask_user": ask_user_fn},
    )
    result = await agent.run("你好", user_id="u1", session_id="s1", emitter=emitter)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.models import Model

from agent_sdk.config import (
    AGENT_FS_DIR,
    MCP_CONFIG_PATH,
    SKILL_DIRS,
    CompactConfig as SdkCompactConfig,
    MemoryConfig,
    ModelConfig,
    ToolConfig,
    TranscriptConfig,
    get_agent_name,
)
from agent_sdk.prompt_loader import PromptLoader, PromptResult

logger = logging.getLogger(__name__)


class Agent:
    """纯逻辑层 Agent，封装 agent loop + 所有核心服务。

    主项目的 main agent、同进程 subagent、独立进程 subagent 都使用此类，
    区别只是配置不同。
    """

    def __init__(
        self,
        # ── 用户直接提供 ──
        prompt_loader: PromptLoader,
        tools: ToolConfig | None = None,
        # ── config 驱动，框架内部构建 service ──
        model: Model | ModelConfig | None = None,
        memory_config: MemoryConfig | None = None,
        transcript_config: TranscriptConfig | None = None,
        compact_config: SdkCompactConfig | None = None,
        # ── 运行参数 ──
        max_iterations: int = 25,
        agent_name: str | None = None,
    ) -> None:
        self._prompt_loader = prompt_loader
        self._tools = tools
        self._model_config = model
        self._memory_config = memory_config or MemoryConfig()
        self._transcript_config = transcript_config or TranscriptConfig()
        self._compact_config = compact_config or SdkCompactConfig()
        self._max_iterations = max_iterations
        self._agent_name = agent_name or get_agent_name()

        # 延迟构建的内部对象
        self._pydantic_model: Model | None = None
        self._memory_service: Any = None
        self._transcript_service: Any = None
        self._context_service: Any = None

    def _build_model(self) -> Model:
        """根据配置构建 Pydantic AI Model"""
        if self._pydantic_model is not None:
            return self._pydantic_model

        if isinstance(self._model_config, Model):
            self._pydantic_model = self._model_config
        elif isinstance(self._model_config, ModelConfig):
            self._pydantic_model = _create_model_from_config(self._model_config)
        else:
            # None → 使用环境变量默认配置
            self._pydantic_model = _create_model_from_config(ModelConfig())
        return self._pydantic_model

    def _build_tool_map(self) -> tuple[list[str], dict[str, Any]]:
        """构建 available_tools 和 tool_map"""
        if self._tools is None:
            return [], {}
        tool_map: dict[str, Any] = {}
        if self._tools.manual:
            tool_map.update(self._tools.manual)
        # MCP 工具在 run() 中动态加载
        available = list(tool_map.keys())
        # include/exclude 过滤
        if self._tools.include is not None:
            available = [t for t in available if t in self._tools.include]
        if self._tools.exclude is not None:
            available = [t for t in available if t not in self._tools.exclude]
        return available, tool_map

    def _build_memory_service(self) -> Any:
        """根据 MemoryConfig 构建 MemoryMessageService"""
        if self._memory_service is not None:
            return self._memory_service

        from agent_sdk.config import get_user_fs_backend

        if self._memory_config.backend == "sqlite":
            from agent_sdk._agent.memory.sqlite_memory_message_service import SqliteMemoryMessageService
            self._memory_service = SqliteMemoryMessageService(self._memory_config.data_dir)
        else:
            from agent_sdk._agent.memory.file_memory_message_service import FileMemoryMessageService
            self._memory_service = FileMemoryMessageService(get_user_fs_backend())
        return self._memory_service

    def _build_transcript_service(self) -> Any:
        """根据 TranscriptConfig 构建 TranscriptService"""
        if self._transcript_service is not None:
            return self._transcript_service

        from agent_sdk._agent.message.transcript_service import TranscriptService
        from agent_sdk.config import get_user_fs_backend

        self._transcript_service = TranscriptService(get_user_fs_backend())
        return self._transcript_service

    def _build_compact_config(self) -> Any:
        """将 SDK CompactConfig 转换为内部 CompactConfig"""
        from agent_sdk._agent.compact.config import CompactConfig as InternalCompactConfig
        return InternalCompactConfig(
            context_window=self._compact_config.context_window,
            output_reserve=self._compact_config.reserve_output_tokens,
        )

    async def run(
        self,
        message: str,
        user_id: str,
        session_id: str,
        emitter: Any,
        *,
        temporal_client: Any = None,
        request_context: Any = None,
    ) -> str | None:
        """执行一轮对话，内部调用 agent loop。

        Args:
            message: 用户消息
            user_id: 用户 ID
            session_id: 会话 ID
            emitter: EventEmitter 实例
            temporal_client: Temporal 客户端（interrupt 用）
            request_context: 请求上下文（位置、车辆等）

        Returns:
            最终响应文本，或 None
        """
        from agent_sdk._agent.agent_message import AgentMessage, from_model_messages
        from agent_sdk._agent.compact.compactor import Compactor
        from agent_sdk._agent.deps import AgentDeps
        from agent_sdk._agent.file_state import FileStateTracker
        from agent_sdk._agent.loop import LoopContext, create_agent, run_agent_loop, _make_summarize_fn
        from agent_sdk._agent.message.attachment_collector import AttachmentCollector
        from agent_sdk._agent.message.pre_model_call_service import PreModelCallMessageService
        from agent_sdk._agent.skills.invoked_store import InvokedSkillStore
        from agent_sdk._agent.skills.registry import SkillRegistry
        from agent_sdk._agent.skills.tool import invoke_skill
        from agent_sdk._common.session_request_task import SessionRequestTask
        from agent_sdk.config import create_session_backend, get_user_fs_backend

        # 1. 加载 prompt
        prompt_result: PromptResult = await self._prompt_loader.load(user_id, session_id)

        # 2. 构建 model
        model = self._build_model()

        # 3. 构建工具
        available_tools, tool_map = self._build_tool_map()

        # 4. 构建 deps
        file_state_tracker = FileStateTracker()
        backend = create_session_backend(user_id, session_id)

        deps = AgentDeps(
            session_id=session_id,
            user_id=user_id,
            available_tools=available_tools,
            tool_map=tool_map,
            backend=backend,
            file_state_tracker=file_state_tracker,
            emitter=emitter,
            temporal_client=temporal_client,
            request_context=request_context,
        )

        # 5. 构建服务
        memory_service = self._build_memory_service()
        transcript_service = self._build_transcript_service()
        internal_compact_config = self._build_compact_config()

        # 6. 创建 pydantic_ai Agent
        pydantic_agent = create_agent(
            model,
            system_prompt=prompt_result.system_prompt if prompt_result.system_prompt else None,
        )

        # 7. 构建 Compactor
        compactor = Compactor(
            config=internal_compact_config,
            user_id=user_id,
            session_id=session_id,
            summarize_fn=_make_summarize_fn(pydantic_agent),
        )

        # 8. Context messages（来自 prompt_loader）
        context_messages: list[ModelRequest] = list(prompt_result.context_messages)

        # 9. 请求上下文 diff
        if request_context is not None and self._context_service is not None:
            changed = await self._context_service.diff(user_id, session_id, request_context)
            if changed:
                context_text = self._context_service.format_changed(changed)
                context_messages.append(ModelRequest(
                    parts=[UserPromptPart(content=context_text)],
                    metadata={"is_meta": True, "source": "request_context"},
                ))
            await self._context_service.set(user_id, session_id, request_context)
            deps.request_context = request_context

        # 10. Attachment collector
        attachment_collector = AttachmentCollector(file_state_tracker)

        # 11. Skill 系统
        skill_registry: SkillRegistry | None = None
        invoked_store: InvokedSkillStore | None = None
        if any(os.path.isdir(d) for d in SKILL_DIRS):
            skill_registry = SkillRegistry.load(SKILL_DIRS)
            invoked_store = InvokedSkillStore(get_user_fs_backend(), user_id, session_id)
            await invoked_store.load()
            if skill_registry.has_skills():
                deps.skill_registry = skill_registry
                deps.invoked_skill_store = invoked_store
                deps.available_tools = [
                    t for t in deps.available_tools if t != "Skill"
                ] + ["Skill"]
                deps.tool_map["Skill"] = invoke_skill  # type: ignore[assignment]

        # 12. PreModelCallMessageService
        pre_call_service = PreModelCallMessageService(
            compactor=compactor,
            context_messages=context_messages,
            attachment_collector=attachment_collector,
            skill_registry=skill_registry if skill_registry and skill_registry.has_skills() else None,
            invoked_skill_store=invoked_store if skill_registry and skill_registry.has_skills() else None,
            system_prompt=prompt_result.system_prompt,
        )

        # 13. MCP toolsets
        mcp_toolsets = None
        if os.path.isfile(MCP_CONFIG_PATH):
            from agent_sdk._agent.mcp.loader import load_mcp_toolsets
            from agent_sdk.config import get_agent_fs_backend
            mcp_toolsets = await load_mcp_toolsets(get_agent_fs_backend())

        # 14. 加载历史
        agent_history: list[AgentMessage] = await memory_service.load(user_id, session_id)

        # 15. 创建 task
        task = SessionRequestTask(
            session_id=session_id,
            message=message,
            user_id=user_id,
            sinker=None,  # type: ignore[arg-type]
            context=request_context,
        )

        # 16. 组装 LoopContext 并运行
        ctx = LoopContext(
            agent=pydantic_agent,
            deps=deps,
            emitter=emitter,
            task=task,
            pre_call_service=pre_call_service,
            memory_service=memory_service,
            transcript_service=transcript_service,
            agent_history=agent_history,
            mcp_toolsets=mcp_toolsets if mcp_toolsets else None,
            max_iterations=self._max_iterations,
            agent_name=self._agent_name,
        )

        return await run_agent_loop(ctx)


def _create_model_from_config(config: ModelConfig) -> Model:
    """从 ModelConfig 构建 Pydantic AI Model"""
    from openai import AsyncAzureOpenAI, AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    if config.provider == "azure":
        client: AsyncOpenAI = AsyncAzureOpenAI(
            azure_endpoint=config.azure_endpoint,
            api_key=config.azure_api_key,
            api_version=config.azure_api_version,
        )
        provider = OpenAIProvider(openai_client=client)
        return OpenAIChatModel(config.azure_deployment_name, provider=provider)
    else:
        client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url or None,
        )
        provider = OpenAIProvider(openai_client=client)
        return OpenAIChatModel(config.model_name, provider=provider)
