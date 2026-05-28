"""
CrossOrgCollaborator — Organization間連携 (E-08)
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass
class CollaborationRequest:
    request_id: str
    source_org: str
    target_org: str
    task_description: str
    status: str


class CrossOrgCollaborator:
    def __init__(self):
        self._requests: list[CollaborationRequest] = []

    def request_collaboration(self, source_org: str, target_org: str, task: str) -> CollaborationRequest:
        request = CollaborationRequest(
            request_id=f"collab:{uuid4()}",
            source_org=source_org,
            target_org=target_org,
            task_description=task,
            status="pending",
        )
        self._requests.append(request)
        return request

    def get_pending_requests(self, org_name: str) -> list[CollaborationRequest]:
        return [
            request
            for request in self._requests
            if request.target_org == org_name and request.status == "pending"
        ]

    def accept_collaboration(self, request_id: str) -> bool:
        for request in self._requests:
            if request.request_id == request_id:
                request.status = "accepted"
                return True
        return False
