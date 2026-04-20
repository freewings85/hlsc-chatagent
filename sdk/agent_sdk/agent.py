"""Agent：纯逻辑层，封装 agent loop + 所有核心服务

使用方式：
    from agent_sdk import Agent, StaticPromptLoader

    agent = Agent(
        prompt_loader=StaticPromptLoader("你是一个助手"),
        tools={"my_tool": my_tool_fn},
    )
    result = await agent.run("你好", user_id="u1", session_id="s1", emitter=emitter)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Protocol

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


class BeforeAgentRunHook(Protocol):
    """Agent 运行前钩子签名。"""

    async def __call__(
        self,
        user_id: str,
        session_id: str,
        deps: Any,
        message: str,
    ) -> None: ...


class AfterRunHook(Protocol):
    """Agent 成功运行后钩子签名。

    仅在主 agent 请求成功完成且 transcript 持久化后调用。
    失败、取消、子 agent 均不触发。
    """

    async def __call__(self, context: Any) -> None: ...


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
        context_formatter: Any = None,
        # ── config 驱动，框架内部构建 service ──
        model: Model | ModelConfig | None = None,
        memory_config: MemoryConfig | None = None,
        transcript_config: TranscriptConfig | None = None,
        compact_config: SdkCompactConfig | None = None,
        # ── 运行参数 ──
        max_iterations: int = 25,
        max_tool_errors_per_turn: int = 2,
        agent_name: str | None = None,
        before_agent_run_hook: BeforeAgentRunHook | None = None,
        after_run_hooks: list[AfterRunHook] | None = None,
    ) -> None:
        self._prompt_loader = prompt_loader
        self._tools = tools
        self._context_formatter = context_formatter
        self._model_config = model
        self._memory_config = memory_config or MemoryConfig()
        self._transcript_config = transcript_config or TranscriptConfig()
        self._compact_config = compact_config or SdkCompactConfig()
        self._max_iterations = max_iterations
        self._max_tool_errors = max_tool_errors_per_turn
        self._agent_name = agent_name or get_agent_name()
        self._before_agent_run_hook = before_agent_run_hook
        self._after_run_hooks: list[AfterRunHook] = after_run_hooks or []

        # 延迟构建的内部对象
        self._pydantic_model: Model | None = None
        self._memory_service: Any = None
        self._transcript_service: Any = None

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

        from agent_sdk._config.settings import get_inner_storage_backend

        if self._memory_config.backend == "sqlite":
            from agent_sdk._agent.memory.sqlite_memory_message_service import SqliteMemoryMessageService
            self._memory_service = SqliteMemoryMessageService(self._memory_config.data_dir)
        else:
            from agent_sdk._agent.memory.file_memory_message_service import FileMemoryMessageService
            self._memory_service = FileMemoryMessageService(get_inner_storage_backend())
        return self._memory_service

    def _build_transcript_service(self) -> Any:
        """根据 TranscriptConfig 构建 TranscriptService"""
        if self._transcript_service is not None:
            return self._transcript_service

        from agent_sdk._agent.message.transcript_service import TranscriptService
        from agent_sdk._config.settings import get_inner_storage_backend

        self._transcript_service = TranscriptService(get_inner_storage_backend())
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
        fs_tools_backend: Any = None,
        is_sub_agent: bool = False,
        message_history: list | None = None,
        transcript_session_id: str | None = None,
        parent_request_id: str | None = None,
        parent_otel_context: Any = None,
        request_id: str | None = None,
        session_state: dict[str, Any] | None = None,
        parent_tool_call_id: str | None = None,
    ) -> str | None:
        """执行一轮对话（唯一入口，所有场景统一使用）。

        Args:
            message: 用户消息
            user_id: 用户 ID
            session_id: 会话 ID
            emitter: EventEmitter 实例
            temporal_client: Temporal 客户端（interrupt 用）
            request_context: 请求上下文（位置、车辆等）
            fs_tools_backend: fs 工具后端（None 时自动创建 session 级）
            is_sub_agent: 是否子 agent（子 agent 不管理 CHAT_REQUEST_END 等）
            message_history: 消息历史（None 时从持久化加载，[] 表示无历史）
            parent_request_id: 父级 request_id（subagent 场景，用于 trace 关联）
            parent_otel_context: 父级 OTel context（subagent 场景，实现跨服务 trace 关联）
            request_id: 请求端传入的 request_id，不传时自动生成
            session_state: 会话级状态（父 agent 传递给子 agent，共享已确认信息）

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
        from agent_sdk._config.settings import (
            get_fs_config,
            get_fs_tools_backend,
            get_inner_storage_backend,
        )

        # 1. 构建工具
        available_tools, tool_map = self._build_tool_map()

        # 2. 构建 fs_tools_backend
        if fs_tools_backend is None:
            # 默认：session 级隔离（mainagent 场景）
            from agent_sdk.config import create_session_backend
            fs_tools_backend = create_session_backend(user_id, session_id)

        # 3. 构建 deps
        import uuid
        request_id = request_id or uuid.uuid4().hex
        file_state_tracker = FileStateTracker()
        deps = AgentDeps(
            session_id=session_id,
            request_id=request_id,
            user_id=user_id,
            available_tools=available_tools,
            tool_map=tool_map,
            inner_storage_backend=get_inner_storage_backend(),
            fs_tools_backend=fs_tools_backend,
            file_state_tracker=file_state_tracker,
            emitter=emitter,
            temporal_client=temporal_client,
            request_context=request_context,
            session_state=dict(session_state) if session_state else {},
            max_tool_errors=self._max_tool_errors,
            # orchestrator 编排字段由 StageHook 从 request_context.orchestrator 解包到 deps，
            # 不在 Agent.run() 层面传参（见 mainagent/src/business_map_hook.py）
        )

        # Logfire span：将 session_id/request_id 注入 OpenTelemetry trace，
        # 所有子 span（hook、LLM 调用、工具调用）自动继承
        async def _run_request() -> str:
            # 日志函数（循环里没被调用也要能 import，放这里避免循环依赖）
            from agent_sdk._utils.session_logger import (
                log_error as _log_error,
                log_request_end as _log_request_end,
                log_request_start as _log_request_start,
            )

            # 4. 构建 memory_service 并挂到 deps（供 hook 读取历史消息）
            memory_service = self._build_memory_service()
            deps.memory_service = memory_service

            # 5. Session 级 log 入口：尽早打，保证即使后续 PreRunHook / prompt_loader /
            # 初始化失败，logs/<session_id>/execution.log 文件夹和全局 chatagent.log
            # 都有对应记录；后续 run_agent_loop 不再重复调这个
            _log_request_start(
                session_id=session_id,
                user_query=message,
                user_id=user_id,
                request_id=request_id,
                request_context=request_context,
            )

            # 6. 初始化阶段（PreRunHook + prompt_loader + services + ctx 构建）：
            # 任何一步失败都要写 session 级 error log 再冒泡出去
            try:
                # 6a. Agent 运行前钩子（可用于 scene 判定等预处理）
                if self._before_agent_run_hook is not None:
                    await self._before_agent_run_hook(
                        user_id,
                        session_id,
                        deps=deps,
                        message=message,
                    )

                # 6b. 加载 prompt（依赖 deps，可用于动态 AGENT.md 注入）
                prompt_result: PromptResult = await self._prompt_loader.load(
                    user_id,
                    session_id,
                    deps=deps,
                    message=message,
                )

                # 6c. 构建 model
                model = self._build_model()

                # 6d. 构建服务
                transcript_service = self._build_transcript_service()
                internal_compact_config = self._build_compact_config()

                # 6e. 创建 pydantic_ai Agent
                pydantic_agent = create_agent(model)

                # 6f. 构建 Compactor
                compactor = Compactor(
                    config=internal_compact_config,
                    user_id=user_id,
                    session_id=session_id,
                    summarize_fn=_make_summarize_fn(pydantic_agent),
                )

                # 6g. Context messages（来自 prompt_loader）
                context_messages: list[ModelRequest] = list(prompt_result.context_messages)

                # 6h. 请求上下文占位（每次 PreModelCall 重渲，读 deps 最新值）
                if self._context_formatter is not None:
                    context_messages.append(ModelRequest(
                        parts=[],
                        metadata={"is_meta": True, "source": "request_context"},
                    ))
                if request_context is not None:
                    deps.request_context = request_context

                # 6i. Session state 注入
                from agent_sdk._agent.deps import create_session_state_message
                session_state_msg: ModelRequest = create_session_state_message(deps.session_state)
                deps._session_state_msg = session_state_msg
                context_messages.append(session_state_msg)

                # 6j. Attachment collector
                attachment_collector = AttachmentCollector(file_state_tracker)

                # 6k. Skill 系统
                skill_registry: SkillRegistry | None = None
                invoked_store: InvokedSkillStore | None = None
                if any(os.path.isdir(d) for d in SKILL_DIRS):
                    skill_registry = SkillRegistry.load(SKILL_DIRS)
                    invoked_store = InvokedSkillStore(get_inner_storage_backend(), user_id, session_id)
                    await invoked_store.load()
                    if skill_registry.has_skills():
                        deps.skill_registry = skill_registry
                        deps.invoked_skill_store = invoked_store
                        deps.available_tools = [
                            t for t in deps.available_tools if t != "Skill"
                        ] + ["Skill"]
                        deps.tool_map["Skill"] = invoke_skill  # type: ignore[assignment]

                # 6l. PreModelCallMessageService
                pre_call_service = PreModelCallMessageService(
                    compactor=compactor,
                    context_messages=context_messages,
                    attachment_collector=attachment_collector,
                    skill_registry=skill_registry if skill_registry and skill_registry.has_skills() else None,
                    invoked_skill_store=invoked_store if skill_registry and skill_registry.has_skills() else None,
                    system_prompt=prompt_result.system_prompt,
                    context_formatter=self._context_formatter,
                    request_context=request_context,
                )

                # 6m. MCP toolsets
                mcp_toolsets = None
                if os.path.isfile(MCP_CONFIG_PATH):
                    from agent_sdk._agent.mcp.loader import load_mcp_toolsets
                    from agent_sdk.config import get_agent_fs_backend
                    mcp_toolsets = await load_mcp_toolsets(get_agent_fs_backend())

                # 6n. 加载历史
                agent_history: list[AgentMessage] = []
                if message_history is not None:
                    agent_history = from_model_messages(message_history)
                else:
                    agent_history = await memory_service.load(user_id, session_id)

                # 6o. 创建 task
                task = SessionRequestTask(
                    session_id=session_id,
                    message=message,
                    user_id=user_id,
                    sinker=None,  # type: ignore[arg-type]
                    request_id=request_id,
                    context=request_context,
                )

                # 6p. 组装 LoopContext
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
                    agent_name=self._agent_name or "main",
                    is_sub_agent=is_sub_agent,
                    transcript_session_id=transcript_session_id,
                    parent_tool_call_id=parent_tool_call_id,
                )
            except Exception as init_exc:
                _log_error(
                    f"Agent 初始化失败: {init_exc}",
                    session_id=session_id,
                    request_id=request_id,
                    exc=init_exc,
                )
                _log_request_end(
                    session_id=session_id,
                    success=False,
                    error=str(init_exc),
                    request_id=request_id,
                )
                # 子 agent 不管理 emitter；主 agent 要发 ERROR + CHAT_REQUEST_END
                # 并关闭 emitter，否则前端 SSE 一直挂着等事件
                if not is_sub_agent:
                    from agent_sdk._event.event_model import EventModel
                    from agent_sdk._event.event_type import EventType
                    await emitter.emit(EventModel(
                        session_id=session_id,
                        request_id=request_id,
                        type=EventType.ERROR,
                        data={"message": str(init_exc)},
                        agent_name=self._agent_name or "main",
                    ))
                    await emitter.emit(EventModel(
                        session_id=session_id,
                        request_id=request_id,
                        type=EventType.CHAT_REQUEST_END,
                        data={"user_id": user_id},
                        finish_reason="error",
                        agent_name=self._agent_name or "main",
                    ))
                    await emitter.close()
                raise

            # 7. 跑循环（run_agent_loop 内部自己 log_request_end）
            from agent_sdk._agent.loop import RunLoopResult

            loop_result: RunLoopResult = await run_agent_loop(ctx)

            if not is_sub_agent and self._after_run_hooks:
                from agent_sdk._agent.hooks import AfterRunContext

                hook_ctx = AfterRunContext(
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                    result=loop_result,
                )
                for hook in self._after_run_hooks:
                    hook_task = asyncio.create_task(
                        hook(hook_ctx),
                        name=f"after-run-hook-{type(hook).__name__}-{request_id[:8]}",
                    )
                    try:
                        await asyncio.shield(hook_task)
                    except asyncio.CancelledError:
                        logger.warning(
                            "after_run_hook %s 在外层任务取消后继续后台执行",
                            type(hook).__name__,
                        )
                    except Exception:
                        logger.warning(
                            "after_run_hook %s 执行异常，已跳过",
                            type(hook).__name__,
                            exc_info=True,
                        )

            return loop_result.final_response

        try:
            import logfire
            span_attrs: dict[str, Any] = {
                "session_id": session_id,
                "request_id": request_id,
                "user_id": user_id,
                "agent_name": self._agent_name,
                "is_sub_agent": is_sub_agent,
                "user_message": message[:50] if message else "",
            }
            if parent_request_id:
                span_attrs["parent_request_id"] = parent_request_id

            if parent_otel_context is not None:
                # 在父级 OTel context 下创建 span，实现跨服务 trace 关联
                from opentelemetry.context import attach, detach
                token = attach(parent_otel_context)
                try:
                    with logfire.span("agent_request", **span_attrs):
                        return await _run_request()
                finally:
                    detach(token)
            else:
                with logfire.span("agent_request", **span_attrs):
                    return await _run_request()
        except ImportError:
            return await _run_request()


def _create_model_from_config(config: ModelConfig) -> Model:
    """从 ModelConfig 构建 Pydantic AI Model"""
    from openai import AsyncAzureOpenAI, AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
    from pydantic_ai.providers.openai import OpenAIProvider

    use_responses_api = config.api_style == "responses"

    if config.provider == "azure":
        client: AsyncOpenAI = AsyncAzureOpenAI(
            azure_endpoint=config.azure_endpoint,
            api_key=config.azure_api_key,
            api_version=config.azure_api_version,
        )
        provider = OpenAIProvider(openai_client=client)
        if use_responses_api:
            return OpenAIResponsesModel(config.azure_deployment_name, provider=provider)
        return OpenAIChatModel(config.azure_deployment_name, provider=provider)
    else:
        client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url or None,
        )
        provider = OpenAIProvider(openai_client=client)
        if use_responses_api:
            return OpenAIResponsesModel(config.model_name, provider=provider)
        return OpenAIChatModel(config.model_name, provider=provider)
