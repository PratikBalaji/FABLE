"""Unit tests for the agent bus."""
import pytest
from backend.core.bus import AgentBus, AgentMessage, TaskContext


@pytest.fixture
def bus():
    return AgentBus()


@pytest.mark.asyncio
async def test_dispatch_registered_agent(bus):
    async def mock_handler(ctx: TaskContext) -> AgentMessage:
        return AgentMessage(role="test", content="hello")

    bus.register("test", mock_handler)
    ctx = TaskContext(task_id="t1", domain="code_review", input="review this")
    msg = await bus.dispatch("test", ctx)
    assert msg.role == "test"
    assert msg.content == "hello"
    assert len(ctx.history) == 1


@pytest.mark.asyncio
async def test_dispatch_unregistered_raises(bus):
    ctx = TaskContext(task_id="t2", domain="code_review", input="review this")
    with pytest.raises(KeyError):
        await bus.dispatch("nonexistent", ctx)


@pytest.mark.asyncio
async def test_run_collaboration_order(bus):
    order = []

    for role in ["a", "b", "c"]:
        r = role
        async def handler(ctx, _r=r):
            order.append(_r)
            return AgentMessage(role=_r, content=_r)
        bus.register(role, handler)

    ctx = TaskContext(task_id="t3", domain="code_review", input="test")
    await bus.run_collaboration(ctx, ["a", "b", "c"])
    assert order == ["a", "b", "c"]
