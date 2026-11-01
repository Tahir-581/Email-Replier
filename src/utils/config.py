from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse, urlunparse

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "data"
REPLIES_FILE = DATA_DIR / "replies.json"
LOGS_FILE = DATA_DIR / "logs.json"

FORM_URLS = {
    "senior_ai_ml": "https://forms.example.com/senior-ai-ml",
    "ai_ml": "https://forms.example.com/ai-ml",
    "full_stack": "https://forms.example.com/full-stack",
    "ai_internship": "https://forms.example.com/ai-internship",
}

INTENT_BUCKETS = {
    1: "Candidate is not interested",
    2: "Candidate is interested, asks for JD or relevant opening",
    3: "Candidate wants remote or hybrid",
    4: "Candidate cannot relocate now, but may later",
    5: "Student, final year, not ready for full-time now",
    6: "Candidate already applied",
    7: "Candidate objects to salary / package",
    8: "Candidate asks about Frontend / Full Stack / MERN / .NET role",
    9: "Candidate refers someone",
    10: "Candidate asks if they can share with their network",
    11: "Candidate asks about company details / legitimacy / culture",
    12: "Candidate asks about interview process",
    13: "Candidate asks about internship",
    14: "Candidate wants part-time / consultancy / freelance / visiting role",
    15: "Candidate asks about office growth / departments / team size / CEO",
    16: "Candidate complains about management / poor experience",
    17: "Candidate asks direct salary / stipend policy question",
    18: "Candidate is ready to relocate or asks about accommodation / relocation process",
    19: "Candidate follows up on application / interview / no response / status",
    20: "Candidate asks for clarification or reports incorrect information",
    21: "Candidate requests a callback",
    22: "Candidate forwards an email chain for review",
    23: "Candidate requests internship / completion certificate",
    24: "Candidate asks about unsupported role such as HR, Content Writer, Graphic Designer",
    25: "Candidate requests interview reschedule",
    26: "Candidate reports website / form issue",
    27: "Candidate asks for feedback after rejection",
    28: "Candidate shares portfolio / CV for non-AI role review",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    LLM_BASE_URL: str = Field(default="https://llm.example.com/v1/chat/completions", validation_alias=AliasChoices("LLM_BASE_URL", "LLM_BASE_URL"))
    LLM_MODEL: str = Field(default="gemma4", validation_alias=AliasChoices("LLM_MODEL", "LLM_MODEL"))
    LLM_TIMEOUT_S: int = Field(default=300, validation_alias=AliasChoices("LLM_TIMEOUT_S", "LLM_TIMEOUT_S"))
    LLM_MAX_CONNECTIONS: int = Field(default=50, validation_alias=AliasChoices("LLM_MAX_CONNECTIONS", "LLM_MAX_CONNECTIONS"))
    LLM_MAX_KEEPALIVE_CONNECTIONS: int = Field(default=25, validation_alias=AliasChoices("LLM_MAX_KEEPALIVE_CONNECTIONS", "LLM_MAX_KEEPALIVE_CONNECTIONS"))
    LLM_MAX_CONCURRENCY: int = Field(default=50, validation_alias=AliasChoices("LLM_MAX_CONCURRENCY", "LLM_MAX_CONCURRENCY"))
    LLM_HEALTH_CHECK_ENABLED: bool = Field(default=True, validation_alias=AliasChoices("LLM_HEALTH_CHECK_ENABLED", "LLM_HEALTH_CHECK_ENABLED"))
    LLM_SUPPORTS_SYSTEM_ROLE: bool = Field(default=False, validation_alias=AliasChoices("LLM_SUPPORTS_SYSTEM_ROLE", "LLM_SUPPORTS_SYSTEM_ROLE"))
    LLM_INTENT_CLASSIFIER_MODEL: str = Field(default="", validation_alias=AliasChoices("LLM_INTENT_CLASSIFIER_MODEL", "LLM_INTENT_CLASSIFIER_MODEL"))
    LLM_POLICY_MODEL: str = Field(default="", validation_alias=AliasChoices("LLM_POLICY_MODEL", "LLM_POLICY_MODEL"))
    LLM_EMAIL_WRITER_MODEL: str = Field(default="", validation_alias=AliasChoices("LLM_EMAIL_WRITER_MODEL", "LLM_EMAIL_WRITER_MODEL"))
    # Max concurrent intent pair-check LLM calls per email.
    INTENT_PAIR_CHECK_CONCURRENCY: int = Field(
        default=12,
        validation_alias=AliasChoices("INTENT_PAIR_CHECK_CONCURRENCY", "INTENT_PAIR_CHECK_CONCURRENCY"),
    )
    # Max emails processed in parallel per batch (1 = sequential).
    EMAIL_BATCH_CONCURRENCY: int = Field(
        default=3,
        validation_alias=AliasChoices("EMAIL_BATCH_CONCURRENCY", "EMAIL_BATCH_CONCURRENCY"),
    )

    REDIS_URL: str = Field(default="", validation_alias=AliasChoices("REDIS_URL", "REDIS_URL"))

    DATABASE_URL: str = ""
    DATABASE_BASE_URL: str = ""

    EMAIL_DB: str = Field(default="email_replier", validation_alias=AliasChoices("EMAIL_DB", "TWITTER_DB"))

    @model_validator(mode='after')
    def construct_database_url(self) -> 'Settings':
        if not self.DATABASE_URL and self.DATABASE_BASE_URL and self.EMAIL_DB:
            base_url = self.DATABASE_BASE_URL.rstrip('/')
            self.DATABASE_URL = f"{base_url}/{self.EMAIL_DB}"

        if self.DATABASE_URL:
            if self.DATABASE_URL.startswith("postgresql://"):
                self.DATABASE_URL = self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif self.DATABASE_URL.startswith("postgresql+psycopg://"):
                self.DATABASE_URL = self.DATABASE_URL.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)

        if self.DATABASE_BASE_URL and self.DATABASE_BASE_URL.startswith("postgresql+psycopg://"):
            self.DATABASE_BASE_URL = self.DATABASE_BASE_URL.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)

        if self.DATABASE_URL:
            parsed = urlparse(self.DATABASE_URL)
            if parsed.scheme.startswith("postgresql"):
                base = parsed._replace(path="/", params="", query="", fragment="")
                derived_base_url = urlunparse(base)

                if not self.DATABASE_BASE_URL:
                    self.DATABASE_BASE_URL = derived_base_url
                else:
                    base_parsed = urlparse(self.DATABASE_BASE_URL)
                    if (base_parsed.hostname, base_parsed.port) != (parsed.hostname, parsed.port):
                        self.DATABASE_BASE_URL = derived_base_url

        return self

    GMAIL_CLIENT_ID: str = Field(default="", validation_alias=AliasChoices("GMAIL_CLIENT_ID", "GMAIL_CLIENT_ID"))
    GMAIL_CLIENT_SECRET: str = Field(default="", validation_alias=AliasChoices("GMAIL_CLIENT_SECRET", "GMAIL_CLIENT_SECRET"))
    GMAIL_REDIRECT_URI: str = Field(default="", validation_alias=AliasChoices("GMAIL_REDIRECT_URI", "GMAIL_REDIRECT_URI"))
    GMAIL_TOKEN_FILE: str = Field(default="token.json", validation_alias=AliasChoices("GMAIL_TOKEN_FILE", "GMAIL_TOKEN_FILE"))

    EMAIL_USERNAME: str = ""
    EMAIL_PASSWORD: str = ""
    EMAIL_IMAP_SERVER: str = "imap.gmail.com"
    EMAIL_IMAP_PORT: int = 993

    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    API_TOKEN_EXPIRE_MINUTES: int = 60

    # Dashboard / API
    API_CORS_ORIGINS: str = Field(
        default="http://localhost:3000",
        validation_alias=AliasChoices("API_CORS_ORIGINS", "API_CORS_ORIGINS"),
    )
    DASHBOARD_ADMIN_EMAIL: str = Field(
        default="admin@example.com",
        validation_alias=AliasChoices("DASHBOARD_ADMIN_EMAIL", "DASHBOARD_ADMIN_EMAIL"),
    )
    DASHBOARD_ADMIN_PASSWORD: str = Field(
        default="admin123",
        validation_alias=AliasChoices("DASHBOARD_ADMIN_PASSWORD", "DASHBOARD_ADMIN_PASSWORD"),
    )
    SETTINGS_FERNET_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("SETTINGS_FERNET_KEY", "SETTINGS_FERNET_KEY"),
    )
    RESEND_API_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("RESEND_API_KEY", "RESEND_API_KEY"),
    )
    RESEND_FROM_EMAIL: str = Field(
        default="",
        validation_alias=AliasChoices("RESEND_FROM_EMAIL", "RESEND_FROM_EMAIL"),
    )

    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "email-replier"
    SLACK_WEBHOOK_URL: str = ""
    LOG_FORMAT: str = "console"
    LOG_LEVEL: str = "INFO"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_TIMEOUT: int = 30
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False

    COMPANY_NAME: str = Field(default="", validation_alias=AliasChoices("COMPANY_NAME", "COMPANY_NAME"))
    COMPANY_WEBSITE: str = Field(default="", validation_alias=AliasChoices("COMPANY_WEBSITE", "COMPANY_WEBSITE"))
    LINKEDIN_URL: str = Field(
        default="https://www.linkedin.com/in/your-recruiter-profile/",
        validation_alias=AliasChoices("LINKEDIN_URL", "LINKEDIN_URL"),
    )
    RECRUITER_NAME: str = Field(default="", validation_alias=AliasChoices("RECRUITER_NAME", "RECRUITER_NAME"))
    RECRUITER_EMAIL: str = Field(default="", validation_alias=AliasChoices("RECRUITER_EMAIL", "RECRUITER_EMAIL"))
    RECRUITER_TITLE: str = Field(default="Head of People & Talent", validation_alias=AliasChoices("RECRUITER_TITLE", "RECRUITER_TITLE"))
    WORK_LOCATION: str = Field(default="", validation_alias=AliasChoices("WORK_LOCATION", "WORK_LOCATION"))
    SALARY_SENIOR: str = Field(default="", validation_alias=AliasChoices("SALARY_SENIOR", "SALARY_SENIOR"))

    SEND_EMAILS_DIRECTLY: bool = Field(default=False, validation_alias=AliasChoices("SEND_EMAILS_DIRECTLY", "SEND_EMAILS_DIRECTLY"))


settings = Settings()

COMPANY_NAME = settings.COMPANY_NAME
COMPANY_WEBSITE = settings.COMPANY_WEBSITE
LINKEDIN_URL = settings.LINKEDIN_URL
RECRUITER_NAME = settings.RECRUITER_NAME
RECRUITER_EMAIL = settings.RECRUITER_EMAIL
RECRUITER_TITLE = settings.RECRUITER_TITLE
WORK_LOCATION = settings.WORK_LOCATION
SALARY_SENIOR = settings.SALARY_SENIOR
SEND_EMAILS_DIRECTLY = settings.SEND_EMAILS_DIRECTLY

SMTP_HOST = settings.SMTP_HOST
SMTP_PORT = settings.SMTP_PORT
SMTP_USERNAME = settings.SMTP_USERNAME
SMTP_PASSWORD = settings.SMTP_PASSWORD
SMTP_FROM = settings.SMTP_FROM
SMTP_TIMEOUT = settings.SMTP_TIMEOUT
SMTP_USE_TLS = settings.SMTP_USE_TLS
SMTP_USE_SSL = settings.SMTP_USE_SSL
