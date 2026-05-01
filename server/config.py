from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


class Settings:
    # --- Infrastructure ---
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017/health_beseen")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    OPENSEARCH_URL: str = os.getenv("OPENSEARCH_URL", "http://localhost:9200")

    # --- LLM ---
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "azure")

    # Azure OpenAI
    AZURE_OPENAI_API_KEY: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_DEPLOYMENT: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-chat")
    AZURE_OPENAI_API_VERSION: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

    # Generic OpenAI-compatible
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

    # Sampling
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1024"))
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    LLM_TOP_P: float = float(os.getenv("LLM_TOP_P", "1.0"))

    # --- Versions ---
    RULE_VERSION: str = "rule_v2.3.1"
    MODEL_VERSION: str = "augment_v1.2"
    APP_VERSION: str = "1.0.0"

    # --- Workspace tools (read_file / bash / SKILL，对齐 OpenClaw 式 agent 工具) ---
    WORKSPACE_ROOT: str = os.getenv(
        "HEALTH_BESEEN_WORKSPACE",
        str(Path(__file__).resolve().parent.parent),
    )
    SKILLS_DIR: str = os.getenv("SKILLS_DIR", "skills")
    ENABLE_BASH_TOOL: bool = os.getenv("ENABLE_BASH_TOOL", "1").lower() not in (
        "0", "false", "no",
    )
    WORKSPACE_BASH_TIMEOUT_SEC: float = float(os.getenv("WORKSPACE_BASH_TIMEOUT_SEC", "60"))
    WORKSPACE_BASH_MAX_OUTPUT_CHARS: int = int(os.getenv("WORKSPACE_BASH_MAX_OUTPUT_CHARS", "80000"))
    READ_FILE_MAX_BYTES: int = int(os.getenv("READ_FILE_MAX_BYTES", "262144"))
    # actone 风格工作区写删与 Office 读取
    WORKSPACE_WRITE_ENABLED: bool = os.getenv("WORKSPACE_WRITE_ENABLED", "1").lower() not in (
        "0", "false", "no",
    )
    WORKSPACE_MAX_WRITE_BYTES: int = int(os.getenv("WORKSPACE_MAX_WRITE_BYTES", "524288"))
    WORKSPACE_DELETE_PROTECTED: str = os.getenv(
        "WORKSPACE_DELETE_PROTECTED",
        ".env,server/.env",
    )
    READ_DOCUMENT_MAX_CHARS: int = int(os.getenv("READ_DOCUMENT_MAX_CHARS", "24000"))
    GREP_MAX_FILES: int = int(os.getenv("GREP_MAX_FILES", "200"))
    GREP_MAX_MATCHES: int = int(os.getenv("GREP_MAX_MATCHES", "80"))
    GLOB_MAX_RESULTS: int = int(os.getenv("GLOB_MAX_RESULTS", "500"))
    WORKSPACE_GREP_SKIP_DIRS: str = os.getenv(
        "WORKSPACE_GREP_SKIP_DIRS",
        ".git,.venv,node_modules,__pycache__,dist,build,.mypy_cache",
    )

    # Agent loop（多轮 tool-use + skill snap）
    AGENT_LOOP_MAX_STEPS: int = int(os.getenv("AGENT_LOOP_MAX_STEPS", "12"))
    AGENT_LOOP_TOOL_BODY_PREVIEW: int = int(os.getenv("AGENT_LOOP_TOOL_BODY_PREVIEW", "4000"))
    AGENT_LOOP_ACTIVE_SNAP_CHARS: int = int(os.getenv("AGENT_LOOP_ACTIVE_SNAP_CHARS", "28000"))


settings = Settings()
