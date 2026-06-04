from __future__ import annotations

import asyncio

from codecraft.approval.manager import ApprovalDecision, ApprovalRequest, ApprovalReviewer


class ThreadApprovalReviewer(ApprovalReviewer):
    def __init__(self) -> None:
        self.pending: dict[str, asyncio.Future[ApprovalDecision]] = {}
        self.requests: dict[str, ApprovalRequest] = {}

    async def review(self, request: ApprovalRequest) -> ApprovalDecision:
        if request.approval_id in self.pending:
            raise RuntimeError(f"duplicate approval request: {request.approval_id}")

        future = asyncio.get_running_loop().create_future()
        self.pending[request.approval_id] = future
        self.requests[request.approval_id] = request
        try:
            return await future
        finally:
            self.pending.pop(request.approval_id, None)

    def decide(self, decision: ApprovalDecision) -> None:
        future = self.pending.get(decision.approval_id)
        if future is None:
            raise KeyError(f"unknown pending approval: {decision.approval_id}")
        if future.done():
            raise RuntimeError(f"approval already decided: {decision.approval_id}")
        future.set_result(decision)

    def list_pending(self) -> list[ApprovalRequest]:
        return [
            self.requests[approval_id]
            for approval_id in self.pending
            if approval_id in self.requests
        ]
