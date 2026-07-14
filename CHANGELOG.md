# Changelog

[简体中文](CHANGELOG.zh-CN.md)

All notable user-facing changes to CodeCraft are recorded here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and package
versions follow [PEP 440](https://peps.python.org/pep-0440/).

## [Unreleased]

## [0.1.0a3] - 2026-07-13

### Added

- Full-screen Textual interface with multi-turn sessions, approval modals,
  session browsing, resume, and trace inspection.
- Incremental repository index, deterministic retrieval routing, repository
  search tool, and retrieval benchmark reports.
- Fixed coding-agent evaluation suite with repeat runs, deterministic grading,
  metrics, and JSON/HTML reports.
- MCP client support and a read-only repository-context MCP server.
- Native macOS/Linux process isolation plus an optional Docker sandbox.
- Context compaction, bounded read-tool concurrency, layered runtime timeouts,
  structured output limits, and per-phase tool timings.

### Changed

- Bare `codecraft` now launches the full-screen TUI instead of the previous
  line-oriented interactive interface.
- The TUI is the sole multi-turn interface. Named CLI commands remain focused on
  one-shot tasks, diagnostics, evaluation, indexing, and services.
- Model events, session inputs, tool arguments, approvals, sandbox decisions,
  and tool results now use stricter runtime contracts.
- CodeCraft is treated as an application rather than a compatibility-focused
  Python SDK during the alpha period.

### Fixed

- Preserved trailing-newline semantics when applying patches.
- Tightened command classification, session cancellation, model stream
  completion, tool batch ordering, error reporting, and secret redaction.

### Compatibility

- This is an alpha release. Session and configuration schemas from earlier
  alpha builds are not guaranteed to remain compatible.

See the [v0.1.0a3 release notes](docs/releases/v0.1.0a3.md) for installation,
validation evidence, and known limitations.

## [0.1.0a2] - 2026-06-11

### Added

- Initial GitHub release workflow, CI matrix, Conventional Commit validation,
  and secret scanning.

### Fixed

- Rendered assistant Markdown correctly in the interactive CLI.

[Unreleased]: https://github.com/Dabuliule/codecraft/compare/v0.1.0a3...HEAD
[0.1.0a3]: https://github.com/Dabuliule/codecraft/compare/v0.1.0a2...v0.1.0a3
[0.1.0a2]: https://github.com/Dabuliule/codecraft/releases/tag/v0.1.0a2
