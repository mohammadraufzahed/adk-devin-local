"""Docker tools backed by the official Docker SDK for Python."""
from __future__ import annotations

import json
import os
import shlex
from typing import Any

import docker
from docker.errors import APIError, DockerException, NotFound


class DockerTools:
    def __init__(self, root: str | os.PathLike[str]):
        self.root = root
        self.allow_mutations = os.environ.get("ADK_DEVIN_ALLOW_MUTATIONS") == "1"
        self._client: docker.DockerClient | None = None

    def _docker(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    @staticmethod
    def _result(value: Any, exit_code: int = 0) -> str:
        return json.dumps({"exit_code": exit_code, "output": value}, ensure_ascii=False, default=str)

    def _error(self, exc: Exception) -> str:
        return self._result(f"Docker API error: {exc}", 1)

    def docker_ps(self, all: bool = False) -> str:
        """List containers using Docker's configured endpoint and context."""
        try:
            rows = []
            for container in self._docker().containers.list(all=all):
                container.reload()
                image = container.image
                image_name = (", ".join(image.tags) or image.short_id) if image else "<missing>"
                rows.append({
                    "id": container.short_id,
                    "name": container.name,
                    "image": image_name,
                    "status": container.status,
                    "state": container.attrs.get("State", {}),
                    "ports": container.attrs.get("NetworkSettings", {}).get("Ports", {}),
                })
            return self._result(rows)
        except (DockerException, APIError) as exc:
            return self._error(exc)

    def docker_logs(self, container: str, lines: int = 80, since: str = "") -> str:
        """Tail logs from a named container; at most 1000 lines."""
        try:
            kwargs: dict[str, Any] = {"tail": max(1, min(lines, 1000)), "timestamps": True}
            if since:
                kwargs["since"] = since
            output = self._docker().containers.get(container).logs(**kwargs).decode("utf-8", errors="replace")
            return self._result(output[-20_000:])
        except (DockerException, APIError, ValueError) as exc:
            return self._error(exc)

    def docker_inspect(self, container: str) -> str:
        """Return Docker's structured container inspection data."""
        try:
            obj = self._docker().containers.get(container)
            obj.reload()
            return self._result(obj.attrs)
        except (DockerException, APIError) as exc:
            return self._error(exc)

    def docker_stats(self, container: str = "") -> str:
        """Return a one-shot resource snapshot for one or all containers."""
        try:
            client = self._docker()
            targets = [client.containers.get(container)] if container else client.containers.list()
            rows = []
            for obj in targets:
                stats = obj.stats(stream=False)
                rows.append({"id": obj.short_id, "name": obj.name, "stats": stats})
            return self._result(rows)
        except (DockerException, APIError) as exc:
            return self._error(exc)

    def docker_manage(self, action: str, container: str) -> str:
        """Start, stop or restart a container; requires host mutation opt-in."""
        if action not in {"start", "stop", "restart"}:
            return "Invalid Docker action."
        if not self.allow_mutations:
            return "Docker mutations are disabled. Set ADK_DEVIN_ALLOW_MUTATIONS=1 in the host environment."
        try:
            obj = self._docker().containers.get(container)
            getattr(obj, action)()
            return self._result(f"Container {container} {action} completed.")
        except (DockerException, APIError) as exc:
            return self._error(exc)

    def docker_exec(self, container: str, command: str) -> str:
        """Run a command in a container; arbitrary execution requires mutation opt-in."""
        if not self.allow_mutations:
            return "docker exec is disabled. Set ADK_DEVIN_ALLOW_MUTATIONS=1 in the host environment to enable it."
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return f"Invalid command: {exc}"
        if not argv or len(argv) > 30:
            return "Invalid command."
        try:
            result = self._docker().containers.get(container).exec_run(argv, demux=True)
            raw_output = result.output
            if isinstance(raw_output, tuple):
                stdout, stderr = raw_output
                output = (stdout or b"").decode("utf-8", errors="replace") + (stderr or b"").decode("utf-8", errors="replace")
            elif isinstance(raw_output, bytes):
                output = raw_output.decode("utf-8", errors="replace")
            else:
                output = ""
            return self._result(output[:20_000], result.exit_code or 0)
        except (DockerException, APIError) as exc:
            return self._error(exc)
