"""OpenTelemetry 工具：修复 logfire SDK 中文转义问题。

logfire/pydantic-ai 在序列化 span attributes 时使用 ensure_ascii=True，
导致中文变成 \\uXXXX。此模块提供一个 SpanProcessor 包装器，在导出前
将转义还原为可读中文。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor

if TYPE_CHECKING:
    from opentelemetry.context import Context
    from opentelemetry.sdk.trace import Span
    from opentelemetry.sdk.trace.export import SpanExporter

# 匹配 \uXXXX 转义序列
_UNICODE_ESCAPE_RE = re.compile(r"\\u[0-9a-fA-F]{4}")


def _decode_unicode_escapes(value: str) -> str:
    """将字符串中的 \\uXXXX 转义还原为 Unicode 字符。

    使用 re.sub 逐个替换，正确处理 surrogate pair（\\uD83D\\uDE00 → emoji）。
    """
    if "\\u" not in value:
        return value
    try:
        # 先处理 surrogate pair（如 \\uD83D\\uDE00）
        def _replace_surrogate_pair(m: re.Match[str]) -> str:
            high = int(m.group(1), 16)
            low = int(m.group(2), 16)
            code_point = 0x10000 + (high - 0xD800) * 0x400 + (low - 0xDC00)
            return chr(code_point)

        result = re.sub(
            r"\\u([dD][89aAbB][0-9a-fA-F]{2})\\u([dD][cCdDeEfF][0-9a-fA-F]{2})",
            _replace_surrogate_pair,
            value,
        )
        # 再处理普通 \uXXXX
        def _replace_single(m: re.Match[str]) -> str:
            return chr(int(m.group(1), 16))

        result = re.sub(r"\\u([0-9a-fA-F]{4})", _replace_single, result)
        return result
    except Exception:
        return value


class UnicodeDecodeSpanProcessor(SpanProcessor):
    """包装另一个 SpanProcessor，导出前解码 span attributes 中的 Unicode 转义。"""

    def __init__(self, exporter: SpanExporter) -> None:
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        self._inner = SimpleSpanProcessor(exporter)

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        self._inner.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        if span.attributes:
            decoded = {}
            for k, v in span.attributes.items():
                if isinstance(v, str) and _UNICODE_ESCAPE_RE.search(v):
                    decoded[k] = _decode_unicode_escapes(v)
                else:
                    decoded[k] = v
            # ReadableSpan.attributes 是只读的，需要通过内部属性修改
            span._attributes = decoded  # type: ignore[attr-defined]
        self._inner.on_end(span)

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)
