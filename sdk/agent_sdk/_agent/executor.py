"""命令执行器抽象层。

所有需要执行命令/代码的工具（bash、execute_code）统一使用此接口。
执行环境可配置：本地 subprocess 或 k8s Pod。

配置（环境变量）：
  CODE_EXECUTOR=local          — 本地 subprocess（默认）
  CODE_EXECUTOR=k8s            — kubectl exec 到常驻 Pod

k8s 模式额外配置：
  K8S_EXECUTOR_NAMESPACE=default
  K8S_EXECUTOR_POD_LABEL=app=code-executor
  K8S_EXECUTOR_CONTAINER=executor
  K8S_EXECUTOR_KUBECONFIG=       — 留空则用默认（~/.kube/config 或 in-cluster）
"""

from __future__ import annotations

import abc
import asyncio
import json
import logging
import os
import shutil
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


class ExecuteResult:
    """命令执行结果"""

    __slots__ = ("stdout", "stderr", "exit_code")

    def __init__(self, stdout: str, stderr: str, exit_code: int) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code

    @property
    def output(self) -> str:
        """stdout + stderr 合并输出"""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(self.stderr)
        return "\n".join(parts)

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class CodeExecutor(abc.ABC):
    """命令执行器抽象基类"""

    @abc.abstractmethod
    async def execute(
        self,
        command: str,
        *,
        timeout: int = 120,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult:
        """执行命令，返回结果。

        Args:
            command: shell 命令
            timeout: 超时秒数
            cwd: 工作目录（仅 local 模式有效）
            env: 额外环境变量
        """
        ...

    async def execute_interactive(
        self,
        command: str,
        *,
        timeout: int = 120,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        on_interrupt: Callable[[dict[str, Any]], Awaitable[str]] | None = None,
    ) -> ExecuteResult:
        """执行命令，支持脚本中断协议。

        脚本通过 stdout 输出 ``__INTERRUPT__:{json}`` 触发中断，
        bash 工具通过 on_interrupt 回调等待用户回复，
        回复写入子进程 stdin，脚本 input() 继续执行。

        没有 on_interrupt 回调时退化为普通 execute()。
        """
        return await self.execute(command, timeout=timeout, cwd=cwd, env=env)


class LocalExecutor(CodeExecutor):
    """本地 subprocess 执行器"""

    async def execute(
        self,
        command: str,
        *,
        timeout: int = 120,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult:
        effective_env = None
        if env:
            effective_env = {**os.environ, **env}

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=effective_env,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout,
            )
            return ExecuteResult(
                stdout=stdout_bytes.decode("utf-8", errors="replace").strip(),
                stderr=stderr_bytes.decode("utf-8", errors="replace").strip(),
                exit_code=proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            proc.kill()
            return ExecuteResult(stdout="", stderr=f"命令超时（{timeout}s）", exit_code=124)
        except OSError as e:
            return ExecuteResult(stdout="", stderr=f"命令启动失败：{e}", exit_code=1)


    _INTERRUPT_PREFIX: str = "__INTERRUPT__:"

    async def execute_interactive(
        self,
        command: str,
        *,
        timeout: int = 120,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        on_interrupt: Callable[[dict[str, Any]], Awaitable[str]] | None = None,
    ) -> ExecuteResult:
        """支持脚本中断协议的交互式执行。

        逐行读取 stdout，检测 __INTERRUPT__: 前缀行：
        1. 解析 JSON 数据，调 on_interrupt 回调等待用户回复
        2. 将回复写入子进程 stdin（附换行符）
        3. 脚本 input() 收到回复后继续执行

        没有 on_interrupt 回调时退化为普通 execute()。
        """
        if on_interrupt is None:
            return await self.execute(command, timeout=timeout, cwd=cwd, env=env)

        effective_env: dict[str, str] | None = None
        if env:
            effective_env = {**os.environ, **env}

        try:
            proc: asyncio.subprocess.Process = await asyncio.create_subprocess_shell(
                command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=effective_env,
            )

            stdout_lines: list[str] = []
            stderr_data: bytes = b""

            async def _read_stdout() -> None:
                assert proc.stdout is not None
                while True:
                    line_bytes: bytes = await proc.stdout.readline()
                    if not line_bytes:
                        break
                    line: str = line_bytes.decode("utf-8", errors="replace").rstrip("\n\r")

                    if line.startswith(self._INTERRUPT_PREFIX):
                        # 解析中断数据，调回调，写回复到 stdin
                        json_str: str = line[len(self._INTERRUPT_PREFIX):]
                        try:
                            interrupt_data: dict[str, Any] = json.loads(json_str)
                        except json.JSONDecodeError:
                            stdout_lines.append(line)
                            continue

                        reply: str = await on_interrupt(interrupt_data)

                        if proc.stdin is not None:
                            proc.stdin.write((reply + "\n").encode("utf-8"))
                            await proc.stdin.drain()
                    else:
                        stdout_lines.append(line)

            async def _read_stderr() -> bytes:
                assert proc.stderr is not None
                return await proc.stderr.read()

            # 并行读取 stdout（逐行）和 stderr（全量）
            try:
                results: tuple[None, bytes] = await asyncio.wait_for(
                    asyncio.gather(_read_stdout(), _read_stderr()),
                    timeout=timeout,
                )
                stderr_data = results[1]
            except asyncio.TimeoutError:
                proc.kill()
                return ExecuteResult(
                    stdout="\n".join(stdout_lines),
                    stderr=f"命令超时（{timeout}s）",
                    exit_code=124,
                )

            await proc.wait()

            return ExecuteResult(
                stdout="\n".join(stdout_lines).strip(),
                stderr=stderr_data.decode("utf-8", errors="replace").strip(),
                exit_code=proc.returncode or 0,
            )

        except OSError as e:
            return ExecuteResult(stdout="", stderr=f"命令启动失败：{e}", exit_code=1)


class K8sExecutor(CodeExecutor):
    """k8s Pod 执行器 — 通过 kubectl exec 在常驻 Pod 中执行命令"""

    def __init__(
        self,
        namespace: str | None = None,
        pod_label: str | None = None,
        container: str | None = None,
        kubeconfig: str | None = None,
    ) -> None:
        self._namespace = namespace or os.getenv("K8S_EXECUTOR_NAMESPACE", "default")
        self._pod_label = pod_label or os.getenv("K8S_EXECUTOR_POD_LABEL", "app=code-executor")
        self._container = container or os.getenv("K8S_EXECUTOR_CONTAINER", "")
        self._kubeconfig = kubeconfig or os.getenv("K8S_EXECUTOR_KUBECONFIG", "")
        self._pod_name: str | None = None

    async def _get_pod_name(self) -> str:
        """获取目标 Pod 名称（缓存）"""
        if self._pod_name is not None:
            return self._pod_name

        kubectl = _find_kubectl()
        cmd = [
            kubectl, "get", "pods",
            "-n", self._namespace,
            "-l", self._pod_label,
            "-o", "jsonpath={.items[0].metadata.name}",
        ]
        if self._kubeconfig:
            cmd.extend(["--kubeconfig", self._kubeconfig])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0 or not stdout.strip():
            error = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"找不到执行 Pod（namespace={self._namespace}, label={self._pod_label}）: {error}"
            )

        self._pod_name = stdout.decode("utf-8").strip()
        logger.info(f"K8sExecutor: using pod {self._pod_name}")
        return self._pod_name

    async def execute(
        self,
        command: str,
        *,
        timeout: int = 120,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult:
        pod_name = await self._get_pod_name()
        kubectl = _find_kubectl()

        # 构建 kubectl exec 命令
        # 如果有 env，用 env KEY=VAL 前缀；如果有 cwd，用 cd 前缀
        shell_cmd = command
        if cwd:
            shell_cmd = f"cd {cwd} && {shell_cmd}"
        if env:
            env_prefix = " ".join(f"{k}={v}" for k, v in env.items())
            shell_cmd = f"env {env_prefix} {shell_cmd}"

        cmd = [
            kubectl, "exec",
            "-n", self._namespace,
            pod_name,
        ]
        if self._container:
            cmd.extend(["-c", self._container])
        if self._kubeconfig:
            cmd.extend(["--kubeconfig", self._kubeconfig])
        cmd.extend(["--", "sh", "-c", shell_cmd])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout,
            )
            return ExecuteResult(
                stdout=stdout_bytes.decode("utf-8", errors="replace").strip(),
                stderr=stderr_bytes.decode("utf-8", errors="replace").strip(),
                exit_code=proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            proc.kill()
            return ExecuteResult(stdout="", stderr=f"命令超时（{timeout}s）", exit_code=124)
        except OSError as e:
            return ExecuteResult(stdout="", stderr=f"kubectl exec 失败：{e}", exit_code=1)


def _find_kubectl() -> str:
    """查找 kubectl 或 k3s kubectl"""
    kubectl = shutil.which("kubectl")
    if kubectl:
        return kubectl
    k3s = shutil.which("k3s")
    if k3s:
        return f"{k3s} kubectl"
    raise RuntimeError("kubectl 未安装，无法使用 k8s 执行器")


# ── 全局单例 ──

_executor: CodeExecutor | None = None


def get_executor() -> CodeExecutor:
    """获取命令执行器（全局单例，根据 CODE_EXECUTOR 环境变量选择）"""
    global _executor
    if _executor is not None:
        return _executor

    executor_type = os.getenv("CODE_EXECUTOR", "local")

    if executor_type == "k8s":
        _executor = K8sExecutor()
        logger.info("CodeExecutor: k8s mode")
    else:
        _executor = LocalExecutor()
        logger.info("CodeExecutor: local mode")

    return _executor
