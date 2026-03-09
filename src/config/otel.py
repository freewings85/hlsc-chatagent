"""OpenTelemetry 工具：修复 pydantic-ai 中文转义 + 取消 attribute 长度限制。

pydantic-ai 在 models/instrumented.py 和 agent/__init__.py 中使用
json.dumps(...) 序列化 span attributes，默认 ensure_ascii=True 导致
中文变成 \\uXXXX。

修复方式：monkey-patch 这两个模块的 json.dumps，强制 ensure_ascii=False。
必须在 logfire.configure() 之前调用 patch_pydantic_ai_json_dumps()。
"""

from __future__ import annotations

import json
from functools import wraps
from typing import Any



def _make_json_dumps_utf8(original: Any = json.dumps) -> Any:
    """创建一个 ensure_ascii=False 的 json.dumps 包装。"""

    @wraps(original)
    def patched(*args: Any, **kwargs: Any) -> str:
        kwargs.setdefault("ensure_ascii", False)
        return original(*args, **kwargs)

    return patched


def patch_pydantic_ai_json_dumps() -> None:
    """Monkey-patch pydantic-ai 模块的 json.dumps，让中文直接输出。"""
    targets = [
        "pydantic_ai.models.instrumented",
        "pydantic_ai.agent",
    ]
    import importlib

    for module_name in targets:
        try:
            mod = importlib.import_module(module_name)
            if hasattr(mod, "json") and hasattr(mod.json, "dumps"):
                # 模块通过 import json 使用，替换 mod.json.dumps
                mod.json = type("json_patched", (), {
                    "__getattr__": lambda self, name: getattr(json, name),
                    "dumps": staticmethod(_make_json_dumps_utf8()),
                })()
        except ImportError:
            pass
