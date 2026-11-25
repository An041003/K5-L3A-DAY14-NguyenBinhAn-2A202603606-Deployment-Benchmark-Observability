from hashlib import sha256
from uuid import uuid4
from fastapi import HTTPException
from redis.exceptions import RedisError
from .config import settings
from .redis_client import r

# Redis server time + one atomic script: no race between workers.
SLIDING_WINDOW = '''
local t = redis.call('TIME')
local now = tonumber(t[1])*1000 + math.floor(tonumber(t[2])/1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now-60000)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1]) then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  return math.max(1, math.ceil((tonumber(oldest[2])+60000-now)/1000))
end
redis.call('ZADD', KEYS[1], now, ARGV[2])
redis.call('PEXPIRE', KEYS[1], 60000)
return 0
'''

def check_rate_limit(key: str) -> None:
    bucket = f'{settings.namespace}:rate:{sha256(key.encode()).hexdigest()}'
    try:
        retry = int(r.eval(SLIDING_WINDOW, 1, bucket, settings.rate_limit_per_minute, uuid4().hex))
    except RedisError as exc:
        raise HTTPException(status_code=503, detail='Rate limiter unavailable') from exc
    if retry:
        raise HTTPException(status_code=429, detail='Rate limit exceeded', headers={'Retry-After': str(retry)})
