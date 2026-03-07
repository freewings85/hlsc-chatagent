"""Compact 配置"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class CompactConfig:
    """压缩阈值配置，从环境变量加载。

    所有 token 数均为估算值（字符数 / 4）。
    """

    # 上下文窗口大小（tokens）
    context_window: int = field(
        default_factory=lambda: int(os.getenv("COMPACT_CONTEXT_WINDOW", "200000")),
    )

    # 输出预留（tokens），计算有效窗口时扣除
    output_reserve: int = field(
        default_factory=lambda: int(os.getenv("COMPACT_OUTPUT_RESERVE", "20000")),
    )

    # --- Microcompact (Layer 1) ---

    # 保留最近 N 个完整 tool result，更早的替换为占位符
    keep_recent_tool_results: int = field(
        default_factory=lambda: int(os.getenv("COMPACT_KEEP_RECENT_TOOL_RESULTS", "3")),
    )

    # 最小节省阈值（tokens），裁剪节省不到这个数就不执行
    min_savings_threshold: int = field(
        default_factory=lambda: int(os.getenv("COMPACT_MIN_SAVINGS_THRESHOLD", "20000")),
    )

    # --- Full Compact (Layer 2) ---

    # 自动压缩缓冲（tokens），有效窗口减去此值为 full compact 触发阈值
    auto_compact_buffer: int = field(
        default_factory=lambda: int(os.getenv("COMPACT_AUTO_BUFFER", "13000")),
    )

    # 是否启用自动压缩
    auto_compact_enabled: bool = field(
        default_factory=lambda: os.getenv("COMPACT_AUTO_ENABLED", "true").lower() == "true",
    )

    # 是否启用 microcompact
    microcompact_enabled: bool = field(
        default_factory=lambda: os.getenv("COMPACT_MICROCOMPACT_ENABLED", "true").lower() == "true",
    )

    @property
    def effective_window(self) -> int:
        """有效窗口 = 上下文窗口 - 输出预留"""
        return self.context_window - self.output_reserve

    @property
    def microcompact_threshold(self) -> int:
        """Microcompact 触发阈值：距有效窗口不到 min_savings_threshold 时"""
        return self.effective_window - self.min_savings_threshold

    @property
    def full_compact_threshold(self) -> int:
        """Full compact 触发阈值（始终 > microcompact_threshold，防止 auto_compact_buffer 过大导致负值）"""
        threshold = self.effective_window - self.auto_compact_buffer
        # 确保 full compact 阈值 > microcompact 阈值：若 auto_compact_buffer 过大导致负值，
        # 则 full compact 在 microcompact 刚刚触发后才可能触发
        return max(threshold, self.microcompact_threshold + 1)
