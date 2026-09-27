# ADK Devin Local — maintainer notes

This is a standalone Python distribution, separate from `pi-devin`. It provides
`adk_devin_local.DevinLocal`, a Google ADK `BaseLlm` adapter for Devin Local.

## Important contract

- This implementation uses Devin Local's undocumented Connect/protobuf endpoints. Keep the compatibility warning prominent; do not describe it as a supported Cognition API.
- Devin credentials must be loaded from the user's CLI credential store; never print or commit secrets.
- Discover selectable model UIDs through the installed `devin models list --format json` command; do not bake a brittle model allowlist into the adapter.
- Keep ADK as the agent runtime: ADK should own sessions and execute returned function calls.
- System instructions are encoded in the dedicated system prompt field; don't merge them into user messages.
- Response framing, EOS handling, JWT acquisition, tool-call mapping, and token limits need regression tests.
- Never run live model calls in routine CI (they can consume paid quota). Live calls are manual opt-in validation.

## Development

```bash
uv sync --extra test
uv run pytest
```

Before changing the private wire protocol, compare behavior with the sibling
`pi-devin` project and verify on at least one authenticated Devin CLI, while
keeping a mocked test suite for CI. Document protocol assumptions and any
unsupported features in `README.md`. Update package version when preparing a
release. The user intends to hand this standalone project to a maintenance agent.
