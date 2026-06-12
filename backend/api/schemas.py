from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    input: str = Field(..., description="Open-ended prompt — any task type")
    # P5a: widened from Literal["code_review","finance"] to free-form str.
    # Downstream code never branched on this field; it is purely a label/tag.
    domain: str = Field(default="general", description="Optional domain tag (default: general)")
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


class AdversarialMeta(BaseModel):
    rounds_completed: int = 0
    max_rounds: int = 2
    judge_verdict: str = "UNKNOWN"
    judge_score: float = 0.0
    judge_rationale: str = ""
    unresolved_issues: list[str] = []


class AdversarialRunResponse(RunResponse):
    adversarial_meta: AdversarialMeta = Field(default_factory=AdversarialMeta)


class IngestRequest(BaseModel):
    text: str
    source: str = "manual"


class IngestResponse(BaseModel):
    chunks_added: int
    source: str


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    model_used: str | None = None
    scores: dict | None = None
    adversarial_run_id: str | None = None
    created_at: str


class MemoryHitOut(BaseModel):
    id: str
    source_type: str
    session_id: str | None = None
    domain: str | None = None
    content: str
    similarity: float
    created_at: str | None = None


class SessionCreateRequest(BaseModel):
    domain: str
    title: str | None = None


class SessionOut(BaseModel):
    id: str
    title: str | None = None
    domain: str
    created_at: str
    updated_at: str


class ProviderAddRequest(BaseModel):
    provider: str
    api_key: str
    label: str | None = None
    base_url: str | None = None


class ProviderConnectionOut(BaseModel):
    id: str
    provider: str
    conn_type: str
    label: str | None = None
    last4: str | None = None
    status: str
    last_validated_at: str | None = None
    created_at: str | None = None


class ProviderTestOut(BaseModel):
    ok: bool
    detail: str | None = None


class OAuthStartOut(BaseModel):
    auth_url: str
    state: str
