from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RETRIEVAL_SUITE_NAME = "codecraft-repository-retrieval-v1"


@dataclass(frozen=True)
class RetrievalCase:
    case_id: str
    category: str
    query: str
    relevant_paths: tuple[str, ...]
    path: str = "."
    mode: Literal["both", "content", "path"] = "both"


_CORPUS = {
    "config/features.py": "FEATURE_FLAG_EXPORT = True\nFEATURE_FLAG_AUDIT = False\n",
    "config/settings.toml": "payment_timeout_ms = 2500\nqueue_workers = 4\n",
    "docs/payments.md": (
        "# Payments\n\nClients must send an idempotency key when creating a charge.\n"
    ),
    "src/api/request.py": (
        "def attach_request_context(request, trace_id):\n"
        "    request.state.trace_id = trace_id\n"
    ),
    "src/auth/permissions.py": (
        "def authorize(actor, action):\n"
        "    allowed_actions = ROLE_PERMISSIONS.get(actor.role, set())\n"
        "    return action in allowed_actions\n"
    ),
    "src/auth/service.py": (
        "def validate_access_token(token):\n"
        "    claims = decode_and_verify(token)\n"
        "    return claims.subject\n"
    ),
    "src/billing/invoice.py": (
        "class InvoiceBuilder:\n"
        "    def create(self, order):\n"
        "        return Invoice(order_id=order.id)\n"
    ),
    "src/db/pool.go": (
        "package db\n\n"
        "const maxReconnectAttempts = 5\n"
        "func openPool(dsn string) *Pool { return connectWithBackoff(dsn) }\n"
    ),
    "src/observability/logging.py": (
        "def bind_trace(logger, trace_id):\n    return logger.bind(trace_id=trace_id)\n"
    ),
    "src/queue/worker.ts": (
        "export function processJob(job: Job) {\n"
        "  if (job.attempts > 4) throw new Error('retry budget exhausted');\n"
        "}\n"
    ),
    "src/services/payment_gateway.ts": (
        "export class PaymentGateway {\n"
        "  async charge(request: ChargeRequest) { return this.client.send(request); }\n"
        "}\n"
    ),
    "tests/test_permissions.py": (
        "def test_viewer_cannot_delete():\n"
        "    assert authorize(viewer, 'delete') is False\n"
    ),
}

_CASES = (
    RetrievalCase(
        "exact-symbol",
        "exact",
        "validate_access_token",
        ("src/auth/service.py",),
        mode="content",
    ),
    RetrievalCase(
        "exact-error-message",
        "exact",
        "retry budget exhausted",
        ("src/queue/worker.ts",),
        mode="content",
    ),
    RetrievalCase(
        "config-key",
        "exact",
        "payment_timeout_ms",
        ("config/settings.toml",),
        mode="content",
    ),
    RetrievalCase(
        "path-fragment",
        "path",
        "invoice",
        ("src/billing/invoice.py",),
        mode="path",
    ),
    RetrievalCase(
        "multi-file-identifier",
        "multi_file",
        "trace_id",
        ("src/api/request.py", "src/observability/logging.py"),
        mode="content",
    ),
    RetrievalCase(
        "case-insensitive-symbol",
        "exact",
        "feature_flag_export",
        ("config/features.py",),
        mode="content",
    ),
    RetrievalCase(
        "scoped-doc-search",
        "scoped",
        "idempotency key",
        ("docs/payments.md",),
        path="docs",
        mode="content",
    ),
    RetrievalCase(
        "natural-language-permissions",
        "semantic",
        "where are user permissions checked",
        ("src/auth/permissions.py",),
        mode="content",
    ),
    RetrievalCase(
        "natural-language-reconnect",
        "semantic",
        "database connection retry policy",
        ("src/db/pool.go",),
        mode="content",
    ),
    RetrievalCase(
        "cross-language-type",
        "exact",
        "PaymentGateway",
        ("src/services/payment_gateway.ts",),
        mode="content",
    ),
)


def get_retrieval_cases() -> tuple[RetrievalCase, ...]:
    """Return the stable retrieval cases used to compare implementations."""
    return _CASES


def seed_retrieval_workspace(workspace: Path) -> None:
    """Create the fixed multi-language corpus used by the retrieval benchmark."""
    workspace.mkdir(parents=True, exist_ok=True)
    for relative_path, content in _CORPUS.items():
        target = workspace / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    ignored = workspace / "__pycache__" / "shadow.py"
    ignored.parent.mkdir(parents=True, exist_ok=True)
    ignored.write_text("validate_access_token = 'ignored'\n", encoding="utf-8")
