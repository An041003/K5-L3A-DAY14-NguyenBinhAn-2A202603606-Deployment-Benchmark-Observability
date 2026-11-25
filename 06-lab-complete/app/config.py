import os
from dataclasses import dataclass, field
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    port: int = field(default_factory=lambda: int(os.getenv('PORT', '8000')))
    environment: str = field(default_factory=lambda: os.getenv('ENVIRONMENT', 'development'))
    agent_api_key: str = field(default_factory=lambda: os.getenv('AGENT_API_KEY', ''))
    redis_url: str = field(default_factory=lambda: os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/0'))
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv('RATE_LIMIT_PER_MINUTE', '10')))
    daily_budget_usd: Decimal = field(default_factory=lambda: Decimal(os.getenv('DAILY_BUDGET_USD', '10')))
    monthly_budget_usd: Decimal = field(default_factory=lambda: Decimal(os.getenv('MONTHLY_BUDGET_USD', '10')))
    log_level: str = field(default_factory=lambda: os.getenv('LOG_LEVEL', 'INFO'))
    namespace: str = field(default_factory=lambda: os.getenv('REDIS_NAMESPACE', 'day14'))

    def __post_init__(self):
        if not 1 <= self.port <= 65535 or self.rate_limit_per_minute < 1:
            raise ValueError('Invalid port/rate limit')
        if any(not x.is_finite() or x < 0 for x in (self.daily_budget_usd, self.monthly_budget_usd)):
            raise ValueError('Invalid budget')

settings = Settings()
