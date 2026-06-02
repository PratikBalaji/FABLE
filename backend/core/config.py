from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OpenRouter (unified LLM gateway)
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Models routed via OpenRouter
    primary_model: str = "anthropic/claude-sonnet-4"      # analyst (deep reasoning)
    secondary_model: str = "openai/gpt-4o-mini"           # critic + synthesizer (cheap)
    critic_model: str = "openai/gpt-4o-mini"

    # RAG
    embedding_model: str = "all-MiniLM-L6-v2"
    vector_store_path: str = "./data/vectorstore"
    chunk_size: int = 512
    chunk_overlap: int = 64
    retrieval_top_k: int = 5

    # AWS
    aws_region: str = "us-east-1"
    s3_bucket: str = "fable-rag-docs"

    # App
    log_level: str = "INFO"
    feedback_db_path: str = "./data/feedback.jsonl"
    app_name: str = "F.A.B.L.E."
    app_url: str = "http://localhost:3000"

    # Adversarial pipeline knobs (used by adversarial_lifecycle.py + adversarial.py)
    adversarial_max_rounds: int = Field(default=2, alias="ADVERSARIAL_MAX_ROUNDS")
    adversarial_judge_threshold: float = 0.80
    planner_model: str = "anthropic/claude-sonnet-4-5"
    actor_model: str = "openai/gpt-4o"
    adv_critic_model: str = "meta-llama/llama-3-70b-instruct"
    validator_model: str = "google/gemini-pro-1.5"
    refiner_model: str = "meta-llama/llama-3-70b-instruct"
    judge_model: str = "anthropic/claude-sonnet-4-5"

    # Multi-user audit (used by guardrails.py for event log)
    use_supabase: bool = Field(default=False, alias="USE_SUPABASE")

    # Guardrails
    guardrails_enabled: bool = Field(default=True, alias="GUARDRAILS_ENABLED")
    guardrails_llm_check: bool = Field(default=True, alias="GUARDRAILS_LLM_CHECK")
    guardrails_post_check: bool = Field(default=True, alias="GUARDRAILS_POST_CHECK")
    guardrails_classifier_model: str = Field(
        default="meta-llama/llama-guard-3-8b",
        alias="GUARDRAILS_CLASSIFIER_MODEL",
    )

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

    # Pseudonymous identity cookie (HMAC-signed via itsdangerous)
    identity_cookie_name: str = Field(default="fable_id", alias="IDENTITY_COOKIE_NAME")
    identity_cookie_secret: str = Field(default="", alias="IDENTITY_COOKIE_SECRET")
    identity_cookie_max_age_days: int = Field(default=365, alias="IDENTITY_COOKIE_MAX_AGE_DAYS")

    # PII redaction (Presidio + optional LLM fallback)
    pii_enabled: bool = Field(default=True, alias="PII_ENABLED")
    pii_llm_fallback: bool = Field(default=True, alias="PII_LLM_FALLBACK")
    pii_classifier_model: str = Field(default="meta-llama/llama-guard-3-8b", alias="PII_CLASSIFIER_MODEL")
    pii_confidence_threshold: float = Field(default=0.40, alias="PII_CONFIDENCE_THRESHOLD")
    pii_spacy_model: str = Field(default="en_core_web_lg", alias="PII_SPACY_MODEL")

    # Memory abstraction — never store raw text in memory_chunks
    memory_abstraction_enabled: bool = Field(default=True, alias="MEMORY_ABSTRACTION_ENABLED")
    memory_abstraction_model: str = Field(default="openai/gpt-4o-mini", alias="MEMORY_ABSTRACTION_MODEL")

    @property
    def resolved_jwks_url(self) -> str:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return ""


settings = Settings()
