# Real-Provider Evaluation Baseline

This document records reproducible real-provider results for the stable
`codecraft-core-v1` suite. Mock-provider tests remain the deterministic CI gate;
these runs measure model plus runtime behavior and may vary between attempts.

## Qwen3.7 Max Preview, 2026-07-13

Command:

```zsh
codecraft eval \
  --provider qwen \
  --model qwen3.7-max-preview \
  --repeat 1 \
  --output-dir outputs/eval-qwen3.7-max-preview-baseline-r1-20260713
```

Environment:

- Provider adapter: `qwen` over the DashScope OpenAI-compatible API
- Model: `qwen3.7-max-preview`
- Suite: `codecraft-core-v1`
- Evaluations: 10 tasks, one attempt per task
- Eval workspaces: local, isolated per attempt, no bash tool, no network tool
- Original full run revision: `62e255a`
- Targeted rerun revision: `62e255a` plus the newline fix described below

Observed metrics from the original run:

| Metric | Value |
| --- | ---: |
| Success rate | 70.0% (7/10) |
| Total duration | 133,357 ms |
| Duration p50 | 13,353 ms |
| Duration p95 | 22,593 ms |
| Input tokens | 195,041 |
| Output tokens | 5,444 |
| Total tokens | 200,485 |
| Tool calls | 29 |
| Tool failures | 1 |
| Runtime errors | 0 |
| Grader failures | 3 |

Per-task results:

| Task | Result | Duration (ms) | Tokens | Tool calls |
| --- | --- | ---: | ---: | ---: |
| `create-welcome-file` | pass | 5,062 | 9,986 | 1 |
| `fix-calculator-bug` | pass | 9,974 | 15,336 | 2 |
| `sync-package-version` | fail | 22,593 | 31,818 | 5 |
| `write-quickstart` | pass | 6,963 | 10,257 | 1 |
| `update-json-settings` | pass | 13,353 | 20,483 | 3 |
| `locate-legacy-token` | pass | 9,334 | 15,124 | 2 |
| `edit-production-timeout` | fail | 14,014 | 15,348 | 2 |
| `deduplicate-timeout-constant` | pass | 21,890 | 41,582 | 7 |
| `follow-project-instructions` | fail | 16,773 | 25,433 | 4 |
| `normalize-name-list` | pass | 13,382 | 15,118 | 2 |

## Failure Analysis

All three original failures completed their turns without runtime errors and
produced semantically correct target content. They failed exact-file graders
because `ApplyPatchTool` treated a missing transport newline at the end of the
patch argument as a request to remove the target file's trailing newline.

The runtime fix now treats the final diff record as newline-terminated unless the
patch includes the standard `\ No newline at end of file` marker. Focused tests
cover both preserving and explicitly removing a trailing newline.

The three failed tasks were rerun once after the fix:

| Task | Result | Finding |
| --- | --- | --- |
| `edit-production-timeout` | pass | Exact output, including trailing newline |
| `follow-project-instructions` | pass | Exact output and protected file preserved |
| `sync-package-version` | fail | Model changed a README protocol compatibility statement that was not a package version declaration |

The targeted rerun is diagnostic evidence, not a replacement 10-task baseline.
It shows that the patch newline defect was fixed and also exposes a separate
model-level semantic over-edit. A new full-suite run is required before claiming
a post-fix aggregate success rate.

## Current Conclusions

- The provider, tool loop, repository search, writes, grading, event persistence,
  and trace export work end to end against a real model.
- Exact text preservation is a meaningful grader: it found a runtime defect that
  ordinary success messages and tool exit status did not reveal.
- Input usage is high relative to the tiny workspaces because each sequential tool
  step resends the conversation and tool schemas. Token efficiency is a concrete
  optimization target.
- The multi-file task is model-sensitive and should be repeated before attributing
  its result to a stable model capability.
