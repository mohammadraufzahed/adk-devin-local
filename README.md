# ADK Devin Local (experimental)

An unofficial experimental **Google Agent Development Kit (ADK) model adapter** for Devin Local. ADK remains the agent runtime and owns tool execution; Devin Local supplies model inference, similar to [`pi-devin-local`](https://github.com/mohammadraufzahed/pi-devin).

> **Compatibility warning:** This adapter uses Devin Local's private, undocumented Connect/protobuf endpoints. Cognition does not support or guarantee them. Updates can break without notice. Use at your own risk; do not rely on it for production workloads.

## Requirements

- Python 3.10+
- Google ADK (`google-adk`)
- Devin CLI installed and authenticated (`devin auth login`)
- A Devin plan/account with access to Devin Local models

## Install

From a checkout:

```bash
pip install .
```

The package will be published to PyPI after the initial compatibility tests. Install the Devin CLI and sign in using its supported flow; this package reads the CLI's local credentials and never asks you to paste a token.

## Use

Get exact model UIDs from the CLI catalog:

```bash
devin models list --format json
```

Then pass one of those IDs to the ADK model:

```python
from google.adk.agents import LlmAgent
from adk_devin_local import DevinLocal

agent = LlmAgent(
    name="devin_local_agent",
    model=DevinLocal(model="swe-2-high"),  # exact model_uid from the CLI catalog
    instruction="You are a helpful assistant.",
)
```

Credential lookup defaults to `~/.local/share/devin/credentials.toml`, matching the Devin CLI. Optional environment variables:

- `DEVIN_CREDENTIALS`: alternate CLI credential file path.
- `DEVIN_CLI`: explicit CLI binary path (for catalog listing).
- `DEVIN_API_SERVER_URL`: override the API server URL.
- `DEVIN_CLIENT_VERSION`: client version metadata override (default `3.6.27`).

To inspect the current live CLI catalog from Python:

```python
from adk_devin_local import list_models, model_uids
print(model_uids())
```

## ADK tools ported from the Pi plugins

`build_tools(workspace, groups=...)` returns ADK-callable functions for the
workspace/file, Git, Docker, Devbox, GitHub CLI, dependency, CodeGraph, web
search/fetch/watch, memory, wiki, blackboard, project, cron, team mailbox,
Telegram, voice and Jev capabilities. The first implementation registers 103
callables across these groups:

```python
from pathlib import Path
from google.adk.agents import LlmAgent
from adk_devin_local import DevinLocal, GROUPS, build_tools, build_subagent_tools

root = Path.cwd()
agent = LlmAgent(
    name="devin_adk",
    model=DevinLocal(model="swe-2-high"),
    instruction="Work in the configured project. Use tools for file changes and verification.",
    tools=build_tools(root, groups=["files", "git", "web", "codegraph"]),
)
```

For all tool groups, pass `groups=list(GROUPS)`. Prefer an explicit allowlist;
103 functions can consume a substantial model context window. Add native ADK
child-agent delegation with `tools=build_tools(...)+build_subagent_tools(root,
"swe-2-high")` as appropriate. The implementer child gets file tools; research
and review children are read-only.

**Operational notes:** file tools are confined to the configured root. Shell-
like Devbox and destructive/mutating Git, Docker, GitHub, dependency and
CodeGraph actions require `ADK_DEVIN_ALLOW_MUTATIONS=1` in the trusted host
environment (the model cannot set it). GitHub needs authenticated `gh`; Docker,
Devbox, package managers, CodeGraph, Telegram bot credentials, voice binaries,
OpenRouter credentials, and team-mailbox host processes are optional and must
be configured separately. Local memory/wiki/blackboard/project/cron data is
stored beneath `.adk-devin/` by default (override with `ADK_DEVIN_STATE_DIR`).

This is a capability port, **not yet complete behavioral parity** with every
Pi runtime feature: cron tools store/manage definitions but do not run a
scheduler daemon; team/project calls rely on the Pi host mailbox protocol;
voice/STT and Telegram need their optional services; detached child-process
controls are replaced with ADK-managed `AgentTool` delegates. Review the
plugin-specific README before assuming an operation has identical semantics.

## Current limitations

- Experimental private endpoint; not an official Cognition API or ADK integration.
- Model UIDs and catalog come from the installed CLI; explicitly pass an exact UID.
- Image input and tool declarations are translated, but multimodal output, some schema features, and rich reasoning-signature replay are not yet implemented.
- Transport buffers the response before yielding the ADK stream (initial version); token-level latency may be higher than native providers.
- No automatic retries; API use may incur account usage/charges.
- Tests use mocked protocol responses. A real model call is opt-in and can consume paid usage.

## Test and benchmark

```bash
uv sync --extra test
uv run pytest
```

A manual, live comparison harness runs identical arithmetic, JSON-formatting,
and Python coding prompts through ADK and Pi for SWE-1.6 and SWE-2. It can use
paid quota; run only when intended:

```bash
uv run python benchmarks/compare.py
```

The script prints only final answers, deterministic scores, timings, and token
usage; it does not persist model transcripts or reasoning traces.

## License and attribution

MIT. Unofficial community project; not affiliated with Google or Cognition. Protocol research and compatible-client design are informed by the MIT-licensed [`pi-devin-local`](https://github.com/mohammadraufzahed/pi-devin) project. Devin Local's server protocol is proprietary and undocumented.
