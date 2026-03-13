"""AttachmentCollector：从 FileStateTracker 生成 changed_files attachment。

参考 Claude Code 的 gqY (changed_files) 和 ND4 (post-compact restore) 机制：
- 每轮 ModelRequestNode 前，注入外部修改过的文件列表
- full compact 后，注入 compact_result.attachments（最近访问文件恢复）
- attachment 消息标记为 is_meta=True，不写入 transcript

注入顺序（与设计文档 §3.3 一致）：
  1. 移除旧 attachment（上一轮遗留）
  2. 若 compact 产出了 attachments，插入到 [1] 位（context 之后）
  3. 若有 changed_files，追加到消息末尾
"""

from __future__ import annotations

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from agent_sdk._agent.compact.compactor import CompactResult
from agent_sdk._agent.file_state import FileStateTracker
from agent_sdk._agent.message.context_injector import wrap_system_reminder

_ATTACHMENT_SOURCE = "changed_files_attachment"


class AttachmentCollector:
    """生成并注入 changed_files attachment。"""

    def __init__(self, file_state_tracker: FileStateTracker) -> None:
        self._tracker = file_state_tracker

    def inject(self, messages: list[ModelMessage], compact_result: CompactResult) -> None:
        """in-place 注入 attachment 到消息列表。

        顺序：
        1. 移除旧 attachment（source == 'changed_files_attachment'）
        2. 插入 compact_result.attachments（full compact 后恢复文件），位置 [1]
        3. 追加 changed_files attachment（is_meta=True）到末尾
        """
        # 1. 移除旧 attachment
        messages[:] = [
            msg for msg in messages
            if not (
                isinstance(msg, ModelRequest)
                and isinstance(msg.metadata, dict)
                and msg.metadata.get("source") == _ATTACHMENT_SOURCE
            )
        ]

        # 2. compact 恢复 attachments（full compact 产出）
        if compact_result.attachments:
            insert_pos = 1 if len(messages) >= 1 else 0
            for i, attachment in enumerate(compact_result.attachments):
                messages.insert(insert_pos + i, attachment)

        # 3. changed_files attachment
        changed = self._tracker.get_changed_files()
        if not changed:
            return

        lines = ["以下文件在您上次访问后已被外部修改（如需最新内容请重新读取）："]
        for cf in changed:
            lines.append(f"- {cf.path}")
        content = wrap_system_reminder("\n".join(lines))

        messages.append(ModelRequest(
            parts=[UserPromptPart(content=content)],
            metadata={"is_meta": True, "source": _ATTACHMENT_SOURCE},
        ))
