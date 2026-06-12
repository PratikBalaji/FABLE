"""
Serialization helpers for distributed AgentBus.

Handles TaskContext and AgentMessage conversion to/from dicts for HTTP transport
between the coordinator and agent pods in K8s mode.

Important: TaskContext.metadata["router"] (ModelRouter instance) is NOT serializable.
Each pod creates its own ModelRouter from environment. The serialization layer strips
it before transport and the receiving pod injects its own.
"""
from __future__ import annotations

from .bus import AgentMessage, TaskContext

# Keys in metadata that are not JSON-serializable (stripped before transport)
_NON_SERIALIZABLE_KEYS = {"router"}


def serialize_task_context(ctx: TaskContext) -> dict:
    """Serialize a TaskContext for HTTP transport."""
    # Strip non-serializable metadata entries
    safe_metadata = {}
    for k, v in ctx.metadata.items():
        if k in _NON_SERIALIZABLE_KEYS:
            continue
        # ELM declarations: convert to dict form
        if k == "elm_declarations" and hasattr(v, "to_dict"):
            safe_metadata[k] = v.to_dict()
        else:
            safe_metadata[k] = v

    return {
        "task_id": ctx.task_id,
        "domain": ctx.domain,
        "input": ctx.input,
        "history": [serialize_agent_message(m) for m in ctx.history],
        "metadata": safe_metadata,
    }


def deserialize_task_context(data: dict) -> TaskContext:
    """Deserialize a TaskContext from HTTP transport data."""
    metadata = data.get("metadata", {})

    # Reconstruct ELM declarations if present
    if "elm_declarations" in metadata and isinstance(metadata["elm_declarations"], dict):
        from ..elm.declarations import PipelineDeclaration
        metadata["elm_declarations"] = PipelineDeclaration.from_dict(
            metadata["elm_declarations"]
        )

    return TaskContext(
        task_id=data["task_id"],
        domain=data["domain"],
        input=data["input"],
        history=[deserialize_agent_message(m) for m in data.get("history", [])],
        metadata=metadata,
    )


def serialize_agent_message(msg: AgentMessage) -> dict:
    """Serialize an AgentMessage for HTTP transport."""
    return {
        "role": msg.role,
        "content": msg.content,
        "metadata": msg.metadata,
        "timestamp": msg.timestamp,
        "message_id": msg.message_id,
    }


def deserialize_agent_message(data: dict) -> AgentMessage:
    """Deserialize an AgentMessage from HTTP transport data."""
    return AgentMessage(
        role=data["role"],
        content=data["content"],
        metadata=data.get("metadata", {}),
        timestamp=data.get("timestamp", ""),
        message_id=data.get("message_id", ""),
    )
