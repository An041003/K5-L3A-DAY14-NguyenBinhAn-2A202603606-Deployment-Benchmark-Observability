from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from redis.exceptions import RedisError
from .config import settings
from .redis_client import r

# Integer nanodollars avoid floating-point accounting drift.
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006
NANO = 1_000_000_000

def estimate_tokens(text: str) -> int:
    return max(1, (len(text)+3)//4)

def cost_nano(input_tokens: int, output_tokens: int) -> int:
    return input_tokens * 150 + output_tokens * 600

RESERVE = '''
local amount = tonumber(ARGV[1])
for i=1,2 do
  local current = tonumber(redis.call('GET', KEYS[i]) or '0')
  if current + amount > tonumber(ARGV[i+1]) then return 0 end
end
for i=1,2 do
  redis.call('INCRBY', KEYS[i], amount)
  redis.call('EXPIREAT', KEYS[i], ARGV[i+3])
end
return 1
'''
SETTLE = '''
for i=1,2 do
  if redis.call('EXISTS', KEYS[i]) == 1 then
    redis.call('INCRBY', KEYS[i], ARGV[1])
  end
end
return 1
'''

@dataclass(frozen=True)
class Reservation:
    keys: tuple[str, str]
    amount: int

def period_keys(now: datetime):
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Grace period keeps outstanding requests settleable across UTC period boundaries.
    return (f'{settings.namespace}:{{budget}}:day:{now:%Y-%m-%d}',
            f'{settings.namespace}:{{budget}}:month:{now:%Y-%m}'), (int(tomorrow.timestamp())+3600, int(next_month.timestamp())+3600)

def check_budget(input_tokens: int, max_output_tokens: int) -> Reservation:
    keys, expiry = period_keys(datetime.now(timezone.utc))
    amount = cost_nano(input_tokens, max_output_tokens)
    try:
        allowed = r.eval(RESERVE, 2, *keys, amount, int(settings.daily_budget_usd*NANO),
                         int(settings.monthly_budget_usd*NANO), *expiry)
    except RedisError as exc:
        raise HTTPException(status_code=503, detail='Budget store unavailable') from exc
    if not allowed:
        raise HTTPException(status_code=402, detail='Budget exhausted')
    return Reservation(keys, amount)

def record_cost(reservation: Reservation, input_tokens: int, output_tokens: int) -> float:
    actual = cost_nano(input_tokens, output_tokens)
    if actual > reservation.amount:
        raise ValueError('Mock output exceeded reserved maximum')
    try:
        r.eval(SETTLE, 2, *reservation.keys, actual-reservation.amount)
    except RedisError as exc:
        # Reservation remains conservative if settlement fails.
        raise HTTPException(status_code=503, detail='Budget settlement unavailable') from exc
    return actual/NANO

def cancel_reservation(reservation: Reservation) -> None:
    try:
        r.eval(SETTLE, 2, *reservation.keys, -reservation.amount)
    except RedisError:
        pass  # keep the conservative debit; never allow overspend by failing open
