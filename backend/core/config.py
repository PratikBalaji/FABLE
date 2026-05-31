from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

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


settings = Settings()
