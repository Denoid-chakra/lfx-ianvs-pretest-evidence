#!/usr/bin/env python3
"""
Mini Docker sandbox runner for the LFX Ianvs simulation sandbox pre-test.

It runs one command inside a Docker container with CPU, memory, and timeout
limits, then prints a structured JSON result.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
import uuid
from typing import Any, Dict, Optional


def docker_available() -> bool:
    """Return True only when the Docker CLI is installed and daemon is reachable."""
    if shutil.which("docker") is None:
        return False

    probe = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return probe.returncode == 0


def remove_container(container_name: str) -> None:
    """Best-effort cleanup for the named container."""
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def container_was_oom_killed(container_name: str) -> bool:
    """Inspect Docker state before cleanup and detect cgroup OOM kill."""
    inspect = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.OOMKilled}}", container_name],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return inspect.returncode == 0 and inspect.stdout.strip().lower() == "true"


def run_in_sandbox(
    image: str,
    command: str,
    cpu_limit: str,
    memory_limit: str,
    timeout: float,
) -> Dict[str, Any]:
    """Run a command inside Docker and return a structured execution result."""
    started = time.monotonic()
    container_name = f"ianvs-sandbox-{uuid.uuid4().hex[:12]}"

    if not docker_available():
        return {
            "status": "docker_unavailable",
            "exit_code": None,
            "wall_time_s": round(time.monotonic() - started, 3),
            "stdout": "",
            "stderr": "",
            "error": "Docker CLI is missing or Docker daemon is not reachable.",
            "container_name": container_name,
            "image": image,
            "command": command,
            "cpu_limit": cpu_limit,
            "memory_limit": memory_limit,
            "timeout_s": timeout,
        }

    docker_cmd = [
        "docker",
        "run",
        "--name",
        container_name,
        "--network",
        "none",
        "--cpus",
        str(cpu_limit),
        "--memory",
        str(memory_limit),
        "--memory-swap",
        str(memory_limit),
        "--pids-limit",
        "256",
        image,
        "/bin/sh",
        "-lc",
        command,
    ]

    proc = subprocess.Popen(
        docker_cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    timed_out = False
    stdout = ""
    stderr = ""
    exit_code: Optional[int]

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        remove_container(container_name)
        stdout, stderr = proc.communicate()
        exit_code = proc.returncode

    wall_time_s = round(time.monotonic() - started, 3)

    oom_killed = False
    if not timed_out:
        oom_killed = exit_code == 137 or container_was_oom_killed(container_name)

    remove_container(container_name)

    if timed_out:
        status = "timeout"
        error = (
            f"Container exceeded timeout of {timeout} seconds and was killed."
        )
    elif oom_killed:
        status = "oom_killed"
        error = (
            "Container killed due to OOM (exit code 137). "
            "Consider increasing memory_limit."
        )
    elif exit_code == 0:
        status = "success"
        error = ""
    else:
        status = "failed"
        error = f"Container exited with non-zero exit code {exit_code}."

    return {
        "status": status,
        "exit_code": exit_code,
        "wall_time_s": wall_time_s,
        "stdout": stdout,
        "stderr": stderr,
        "error": error,
        "container_name": container_name,
        "image": image,
        "command": command,
        "cpu_limit": cpu_limit,
        "memory_limit": memory_limit,
        "timeout_s": timeout,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a command inside a Docker container with resource limits."
    )
    parser.add_argument("--image", required=True, help="Docker image to run.")
    parser.add_argument(
        "--command",
        required=True,
        help="Command string executed inside the container by /bin/sh -lc.",
    )
    parser.add_argument(
        "--cpu-limit",
        default="1",
        help="Docker CPU limit, passed to docker run --cpus. Example: 1 or 0.5.",
    )
    parser.add_argument(
        "--memory-limit",
        default="256m",
        help="Docker memory limit, passed to docker run --memory. Example: 64m.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Maximum wall-clock runtime in seconds.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_in_sandbox(
        image=args.image,
        command=args.command,
        cpu_limit=args.cpu_limit,
        memory_limit=args.memory_limit,
        timeout=args.timeout,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
