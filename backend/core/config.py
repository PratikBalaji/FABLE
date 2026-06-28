from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OpenRouter (unified LLM gateway)
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_oauth_callback: str = "http://localhost:3000/api/auth/openrouter/callback"
    openrouter_auth_url: str = "https://openrouter.ai/auth"
    openrouter_key_exchange_url: str = "https://openrouter.ai/api/v1/auth/keys"

    # Models routed via OpenRouter
    primary_model: str = "anthropic/claude-sonnet-4-5"     # analyst (deep reasoning)
    secondary_model: str = "openai/gpt-4o-mini"           # critic + synthesizer (cheap)
    critic_model: str = "openai/gpt-4o-mini"

    # RAG
    # P6b: switched from local sentence-transformers all-MiniLM-L6-v2 to OpenAI
    # text-embedding-3-small (truncated to dim=384). Schema vector(384) unchanged.
    embedding_model: str = "all-MiniLM-L6-v2"  # legacy field; informational only
    embeddings_provider: str = Field(default="openai", alias="EMBEDDINGS_PROVIDER")
    embeddings_model: str = Field(default="text-embedding-3-small", alias="EMBEDDINGS_MODEL")
    embeddings_dimensions: int = Field(default=384, alias="EMBEDDINGS_DIMENSIONS")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    # Google Gemini (AI Studio) key — enables embeddings + chat via Gemini's OpenAI-compatible
    # endpoint. When set (or EMBEDDINGS_PROVIDER=google), embeddings route to Gemini.
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    vector_store_path: str = "./data/vectorstore"
    chunk_size: int = 512
    chunk_overlap: int = 64
    retrieval_top_k: int = 5

    # AWS
    aws_region: str = "us-east-1"
    s3_bucket: str = "fable-rag-docs"

    # App
    env: str = Field(default="production", alias="ENV")  # "local" disables auth enforcement
    log_level: str = "INFO"
    feedback_db_path: str = "./data/feedback.jsonl"
    app_name: str = "FABLE"
    app_full_name: str = "Framework for Adversarial Benchmarking and Logic Evaluation"
    app_url: str = "http://localhost:3000"

    # Adversarial pipeline knobs (used by adversarial_lifecycle.py + adversarial.py)
    adversarial_max_rounds: int = Field(default=2, alias="ADVERSARIAL_MAX_ROUNDS")
    adversarial_judge_threshold: float = 0.80
    # Phase 19: run-level self-consistency ensemble. N independent debates run
    # concurrently; the highest judge_score wins. Default 1 = single debate (no change).
    adversarial_ensemble_size: int = Field(default=1, alias="ADVERSARIAL_ENSEMBLE_SIZE")
    # P14: rebalanced (Phase 12) + fixed invalid OpenRouter IDs.
    # meta-llama/llama-3-70b-instruct was NOT routable on OpenRouter (404),
    # forcing a failed call + fallback retry per critic/refiner role per round.
    planner_model: str = "anthropic/claude-sonnet-4-5"
    actor_model: str = "openai/gpt-4o"
    adv_critic_model: str = "anthropic/claude-3.5-haiku"   # was llama-3-70b (invalid)
    validator_model: str = "openai/gpt-4o-mini"             # gemini-2.0-flash not routable
    refiner_model: str = "openai/gpt-4o-mini"               # was llama-3-70b (invalid)
    judge_model: str = "anthropic/claude-sonnet-4-5"

    # Summaries (P14: per-agent off by default — cuts adversarial latency ~12 calls → 1)
    summaries_enabled: bool = Field(default=True, alias="SUMMARIES_ENABLED")
    summaries_per_agent: bool = Field(default=False, alias="SUMMARIES_PER_AGENT")

    # Multi-user audit (used by guardrails.py for event log)
    use_supabase: bool = Field(default=False, alias="USE_SUPABASE")

    # Guardrails
    guardrails_enabled: bool = Field(default=True, alias="GUARDRAILS_ENABLED")
    guardrails_llm_check: bool = Field(default=True, alias="GUARDRAILS_LLM_CHECK")
    guardrails_post_check: bool = Field(default=True, alias="GUARDRAILS_POST_CHECK")
    guardrails_classifier_model: str = Field(
        default="openai/gpt-4o-mini",
        alias="GUARDRAILS_CLASSIFIER_MODEL",
    )
    # Content moderation (hate speech always blocked; profanity gate is optional)
    moderation_enabled: bool = Field(default=True, alias="MODERATION_ENABLED")
    moderation_block_profanity: bool = Field(default=False, alias="MODERATION_BLOCK_PROFANITY")

    # Golden-case reasoning cache (Phase 14)
    golden_cache_enabled: bool = Field(default=True, alias="GOLDEN_CACHE_ENABLED")
    golden_promote_threshold: float = Field(default=0.75, alias="GOLDEN_PROMOTE_THRESHOLD")
    golden_hit_threshold: float = Field(default=0.93, alias="GOLDEN_HIT_THRESHOLD")
    golden_warm_threshold: float = Field(default=0.82, alias="GOLDEN_WARM_THRESHOLD")
    golden_ttl_days: int = Field(default=30, alias="GOLDEN_TTL_DAYS")

    # --- P4a: Identity + PII ----------------------------------------------
    # Supabase project ref (e.g. cldgflwqgyfmanbvuxrg)
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_anon_key: str = Field(default="", alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwks_url: str = Field(default="", alias="SUPABASE_JWKS_URL")
    supabase_jwt_secret: str = Field(default="", alias="SUPABASE_JWT_SECRET")
    use_jwks: bool = Field(default=True, alias="USE_JWKS")
    jwt_audience: str = "authenticated"

    # AES-256-GCM master key (base64 of 32 random bytes) — encrypts provider keys + PII values
    app_encryption_key: str = Field(default="", alias="APP_ENCRYPTION_KEY")
    # F-016 key rotation: optional multi-key map. Format: "3:<b64key>,4:<b64key>" (csv of version:key).
    # APP_ENCRYPTION_KEY_ACTIVE selects which version new ciphertext is written with.
    # When unset, falls back to single-key APP_ENCRYPTION_KEY (v2 format). Decrypt always
    # selects the correct key by the version byte embedded in the ciphertext.
    app_encryption_keys: str = Field(default="", alias="APP_ENCRYPTION_KEYS")
    app_encryption_key_active: int = Field(default=0, alias="APP_ENCRYPTION_KEY_ACTIVE")

    # Pseudonymous identity cookie (HMAC-signed via itsdangerous)
    identity_cookie_name: str = Field(default="fable_id", alias="IDENTITY_COOKIE_NAME")
    identity_cookie_secret: str = Field(default="", alias="IDENTITY_COOKIE_SECRET")
    identity_cookie_max_age_days: int = Field(default=365, alias="IDENTITY_COOKIE_MAX_AGE_DAYS")
    # P6c: cross-origin deploy (Vercel frontend + Cloud Run backend) requires
    # samesite="none". Local dev (same-origin) can keep "lax".
    cookie_samesite: str = Field(default="lax", alias="COOKIE_SAMESITE")
    cookie_secure: bool = Field(default=True, alias="COOKIE_SECURE")

    # PII redaction (regex + optional LLM extraction layer, P6a)
    pii_enabled: bool = Field(default=True, alias="PII_ENABLED")
    pii_llm_fallback: bool = Field(default=True, alias="PII_LLM_FALLBACK")
    pii_classifier_model: str = Field(default="openai/gpt-4o-mini", alias="PII_CLASSIFIER_MODEL")
    pii_confidence_threshold: float = Field(default=0.40, alias="PII_CONFIDENCE_THRESHOLD")
    # Presidio sidecar (Phase 10) — set PRESIDIO_URL to enable; blank = regex+LLM fallback
    presidio_url: str = Field(default="", alias="PRESIDIO_URL")

    # Agentic RAG (Phase 18, CRAG-lite): retrieve → grade → rewrite+retry → graded context
    agentic_rag_enabled: bool = Field(default=True, alias="AGENTIC_RAG_ENABLED")
    agentic_rag_max_hops: int = Field(default=2, alias="AGENTIC_RAG_MAX_HOPS")
    agentic_rag_top_k: int = Field(default=5, alias="AGENTIC_RAG_TOP_K")
    agentic_rag_min_relevant: int = Field(default=2, alias="AGENTIC_RAG_MIN_RELEVANT")

    # Memory abstraction — never store raw text in memory_chunks
    memory_abstraction_enabled: bool = Field(default=True, alias="MEMORY_ABSTRACTION_ENABLED")
    memory_abstraction_model: str = Field(default="openai/gpt-4o-mini", alias="MEMORY_ABSTRACTION_MODEL")

    # ELM (Embedded Language Model) — dynamic role declaration for adversarial pipeline
    elm_enabled: bool = Field(default=False, alias="ELM_ENABLED")
    elm_model_path: str = Field(default="./data/models/phi-3-mini", alias="ELM_MODEL_PATH")
    elm_max_tokens: int = Field(default=1024, alias="ELM_MAX_TOKENS")
    elm_cache_dir: str = Field(default="./data/elm_cache", alias="ELM_CACHE_DIR")
    elm_cache_ttl_hours: int = Field(default=24, alias="ELM_CACHE_TTL_HOURS")

    # Phase 19: orchestrator backend for the agent pipelines. "asyncio" is the native
    # AgentBus (default, baseline/control). "langgraph" routes the adversarial pipeline
    # through the LangGraph StateGraph; "langchain" routes standard mode through LCEL.
    orchestrator: str = Field(default="asyncio", alias="ORCHESTRATOR")

    # Phase 19: LangSmith tracing (optional; auto-emitted by LangChain/LangGraph when
    # enabled). All optional — absence must never crash (Cloud Run safe).
    langchain_tracing_v2: bool = Field(default=False, alias="LANGCHAIN_TRACING_V2")
    langchain_api_key: str = Field(default="", alias="LANGCHAIN_API_KEY")
    langchain_project: str = Field(default="fable", alias="LANGCHAIN_PROJECT")
    langchain_endpoint: str = Field(
        default="https://api.smith.langchain.com", alias="LANGCHAIN_ENDPOINT"
    )

    # Rate limits (per IP; applied on /run and /adversarial-run)
    rate_limit_run: str = Field(default="20/minute", alias="RATE_LIMIT_RUN")
    rate_limit_adv: str = Field(default="5/minute", alias="RATE_LIMIT_ADV")
    # Phase 19: project-wide default limit for every route (per IP). Backstop quota.
    rate_limit_global: str = Field(default="100/minute", alias="RATE_LIMIT_GLOBAL")
    # F-035: max in-flight runs per identity (in-process semaphore). 0 = unlimited.
    max_concurrent_per_identity: int = Field(default=2, alias="MAX_CONCURRENT_PER_IDENTITY")

    # CORS — comma-separated list of allowed origins; default covers local dev.
    # Production: set CORS_ORIGINS=https://your-vercel-app.vercel.app
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    @property
    def trusted_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # Shared token for coordinator→agent pod auth (F-029)
    agent_internal_token: str = Field(default="", alias="AGENT_INTERNAL_TOKEN")

    # Kubernetes distributed mode (local dev only; production stays Cloud Run)
    k8s_mode: bool = Field(default=False, alias="K8S_MODE")
    # F-032: explicit opt-in required to run distributed dispatch under ENV=production.
    k8s_allow_prod: bool = Field(default=False, alias="K8S_ALLOW_PROD")
    k8s_service_registry: str = Field(
        default='{"planning":"http://planning-pod:8001","execution":"http://execution-pod:8002","review":"http://review-pod:8003"}',
        alias="K8S_SERVICE_REGISTRY",
    )

    @property
    def k8s_services(self) -> dict[str, str]:
        """Parse K8S_SERVICE_REGISTRY JSON string into dict."""
        import json
        try:
            return json.loads(self.k8s_service_registry)
        except (json.JSONDecodeError, TypeError):
            return {
                "planning": "http://planning-pod:8001",
                "execution": "http://execution-pod:8002",
                "review": "http://review-pod:8003",
            }

    @model_validator(mode="after")
    def _guard_k8s_in_prod(self) -> "Settings":
        """F-032: refuse distributed K8S_MODE in production unless explicitly allowed."""
        if self.k8s_mode and self.env == "production" and not self.k8s_allow_prod:
            raise ValueError(
                "K8S_MODE=true with ENV=production is blocked. Distributed agent dispatch "
                "is for local dev; production uses Cloud Run. Set K8S_ALLOW_PROD=true to override."
            )
        return self

    @property
    def resolved_jwks_url(self) -> str:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return ""


settings = Settings()
