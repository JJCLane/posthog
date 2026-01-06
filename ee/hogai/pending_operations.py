from datetime import timedelta
from typing import Any, Literal

from django.core.cache import cache

PENDING_OP_TTL = timedelta(minutes=30)
PENDING_OP_PREFIX = "pending_op:"
APPROVED_OP_PREFIX = "approved_op:"
REJECTED_OP_PREFIX = "rejected_op:"

OperationStatus = Literal["pending", "approved", "rejected"]


async def store_pending_operation(
    conversation_id: str,
    proposal_id: str,
    tool_name: str,
    payload: dict[str, Any],
) -> None:
    """Store a pending operation awaiting approval."""
    from posthog.sync import database_sync_to_async

    key = f"{PENDING_OP_PREFIX}{conversation_id}:{proposal_id}"

    @database_sync_to_async
    def _store():
        cache.set(
            key,
            {
                "tool_name": tool_name,
                "payload": payload,
                "conversation_id": conversation_id,
                "proposal_id": proposal_id,
                "status": "pending",
            },
            timeout=int(PENDING_OP_TTL.total_seconds()),
        )

    await _store()


def get_pending_operation(
    conversation_id: str,
    proposal_id: str,
) -> dict[str, Any] | None:
    """Retrieve a pending operation."""
    key = f"{PENDING_OP_PREFIX}{conversation_id}:{proposal_id}"
    return cache.get(key)


def delete_pending_operation(
    conversation_id: str,
    proposal_id: str,
) -> None:
    """Delete a pending operation (after approval or rejection)."""
    key = f"{PENDING_OP_PREFIX}{conversation_id}:{proposal_id}"
    operation = cache.get(key)
    cache.delete(key)
    # Also clean up the approved lookup key if it exists
    if operation and operation.get("tool_name"):
        tool_name = operation["tool_name"]
        approved_key = f"{APPROVED_OP_PREFIX}{conversation_id}:{tool_name}"
        cached_proposal_id = cache.get(approved_key)
        if cached_proposal_id == proposal_id:
            cache.delete(approved_key)


def approve_pending_operation(
    conversation_id: str,
    proposal_id: str,
) -> bool:
    """
    Mark a pending operation as approved.
    Reverse lookup key so the tool can find the approved operation by conversation_id and tool_name.
    Returns True if successful, False if operation not found.
    """
    operation = get_pending_operation(conversation_id, proposal_id)
    if not operation:
        return False

    tool_name = operation.get("tool_name")
    if not tool_name:
        return False

    key = f"{PENDING_OP_PREFIX}{conversation_id}:{proposal_id}"
    operation["status"] = "approved"
    cache.set(key, operation, timeout=int(PENDING_OP_TTL.total_seconds()))

    # Create a reverse lookup key: conversation_id:tool_name -> proposal_id
    # This ensures each tool can have at most one approved operation per conversation
    approved_key = f"{APPROVED_OP_PREFIX}{conversation_id}:{tool_name}"
    cache.set(approved_key, proposal_id, timeout=int(PENDING_OP_TTL.total_seconds()))

    return True


def get_approved_operation_for_conversation(
    conversation_id: str,
    tool_name: str,
) -> dict[str, Any] | None:
    """
    Find an approved operation for this conversation and tool.
    Returns the operation dict if found and approved, None otherwise.
    """
    # Look up the proposal_id from the reverse lookup key (keyed by conversation + tool)
    approved_key = f"{APPROVED_OP_PREFIX}{conversation_id}:{tool_name}"
    proposal_id = cache.get(approved_key)
    if not proposal_id:
        return None

    # Get the operation and verify it's approved
    operation = get_pending_operation(conversation_id, proposal_id)
    if not operation:
        return None

    if operation.get("status") != "approved":
        return None

    return operation


def reject_pending_operation(
    conversation_id: str,
    proposal_id: str,
    feedback: str | None = None,
) -> bool:
    """
    Mark a pending operation as rejected.
    Creates a reverse lookup key so the tool can find the rejected operation.
    Returns True if successful, False if operation not found.
    """
    operation = get_pending_operation(conversation_id, proposal_id)
    if not operation:
        return False

    tool_name = operation.get("tool_name")
    if not tool_name:
        return False

    key = f"{PENDING_OP_PREFIX}{conversation_id}:{proposal_id}"
    operation["status"] = "rejected"
    if feedback:
        operation["feedback"] = feedback
    cache.set(key, operation, timeout=int(PENDING_OP_TTL.total_seconds()))

    # Create a reverse lookup key: conversation_id:tool_name -> proposal_id
    # This ensures each tool can have at most one rejected operation per conversation
    rejected_key = f"{REJECTED_OP_PREFIX}{conversation_id}:{tool_name}"
    cache.set(rejected_key, proposal_id, timeout=int(PENDING_OP_TTL.total_seconds()))

    return True


def get_rejected_operation_for_conversation(
    conversation_id: str,
    tool_name: str,
) -> dict[str, Any] | None:
    """
    Find a rejected operation for this conversation and tool.
    Returns the operation dict if found and rejected, None otherwise.
    """
    # Look up the proposal_id from the reverse lookup key (keyed by conversation + tool)
    rejected_key = f"{REJECTED_OP_PREFIX}{conversation_id}:{tool_name}"
    proposal_id = cache.get(rejected_key)
    if not proposal_id:
        return None

    # Get the operation and verify it's rejected
    operation = get_pending_operation(conversation_id, proposal_id)
    if not operation:
        return None

    if operation.get("status") != "rejected":
        return None

    return operation


def clear_rejected_operation(
    conversation_id: str,
    tool_name: str,
) -> None:
    """Clear the rejected operation lookup key after the tool has handled it."""
    rejected_key = f"{REJECTED_OP_PREFIX}{conversation_id}:{tool_name}"
    proposal_id = cache.get(rejected_key)
    if proposal_id:
        cache.delete(rejected_key)
        # Also delete the pending operation itself
        key = f"{PENDING_OP_PREFIX}{conversation_id}:{proposal_id}"
        cache.delete(key)
