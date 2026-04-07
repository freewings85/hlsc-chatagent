"""OTel bootstrap：bash 子进程自动 trace 传播。

bash 工具在执行 `python script.py` 时自动注入本脚本：
  python _otel_boot.py script.py [args...]

功能：
  1. 从环境变量恢复父级 trace context（traceparent）
  2. 配置 OTLP exporter（同主进程 endpoint）
  3. 自动 instrument httpx
  4. 执行目标脚本（对脚本代码完全透明）
"""

from __future__ import annotations

import os
import sys


def _boot() -> None:
    endpoint: str = os.environ.get("LOGFIRE_ENDPOINT", "")
    traceparent: str = os.environ.get("traceparent", "")
    if not endpoint or not traceparent:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.context import attach
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.propagate import extract
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        provider: TracerProvider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)

        # 从 env 恢复父级 context（bash 工具通过 inject 写入了 traceparent）
        ctx = extract(os.environ)
        attach(ctx)

        # 自动 instrument httpx —— 子进程的所有 httpx 请求都会生成 span
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
    except Exception:
        pass  # OTel 不可用时静默跳过，不影响脚本执行


_boot()

# 执行目标脚本
if len(sys.argv) < 2:
    print("Usage: python _otel_boot.py <script.py> [args...]", file=sys.stderr)
    sys.exit(1)

target: str = sys.argv[1]
sys.argv = sys.argv[1:]

import runpy
runpy.run_path(target, run_name="__main__")
