from pydantic import BaseModel, Field
from typing import Literal


class RunRequest(BaseModel):
    input: str = Field(..., description="Task text, code diff, or financial query")
    domain: Literal["code_review", "finance"] = "code_review"
    pipeline: list[str] | None = Field(
        None, description="Override agent pipeline order. Default: analyst→critic→synthesizer"
    )


class AgentMessageOut(BaseModel):
    role: str
    content: str
    metadata: dict = {}
    timestamp: str
    message_id: str


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    weight: float
    position: dict[str, float]
    runCount: int = 0
    metadata: dict = {}


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: float
    type: str


class GraphStats(BaseModel):
    totalRuns: int
    totalNodes: int
    totalEdges: int
    clusters: int
    concepts: int


class GraphState(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    stats: GraphStats


class RunResponse(BaseModel):
    task_id: str
    domain: str
    pipeline: list[str]
    messages: list[AgentMessageOut]
    scores: dict[str, float] = {}
    model_used: str = ""
    knowledge_graph: GraphState


class IngestRequest(BaseModel):
    text: str
    source: str = "manual"


class IngestResponse(BaseModel):
    chunks_added: int
    source: str
