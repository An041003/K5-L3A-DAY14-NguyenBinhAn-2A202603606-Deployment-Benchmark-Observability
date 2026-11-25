import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from utils.mock_llm import ask as llm_ask, MOCK_RESPONSES
from .auth import verify_api_key
from .config import settings
from .cost_guard import check_budget, record_cost, cancel_reservation, estimate_tokens
from .rate_limiter import check_rate_limit
from .redis_client import redis_healthy, close_redis

logging.basicConfig(level=settings.log_level, format='%(message)s')
logger = logging.getLogger('day14.agent')

def log_event(event: str, **fields):
    logger.info(json.dumps({'ts': datetime.now(timezone.utc).isoformat(), 'lvl': 'INFO', 'event': event, **fields}, ensure_ascii=False))

@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event('startup', environment=settings.environment)
    try:
        yield
    finally:
        # Uvicorn drains in-flight requests before invoking lifespan shutdown.
        close_redis()
        log_event('shutdown')

app = FastAPI(title='Production AI Agent', lifespan=lifespan)
MAX_OUTPUT_TOKENS = max(estimate_tokens(answer) for answers in MOCK_RESPONSES.values() for answer in answers)

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=128)

@app.middleware('http')
async def request_log(request: Request, call_next):
    request_id = uuid.uuid4().hex
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers['X-Request-ID'] = request_id
        return response
    finally:
        route = request.scope.get('route')
        log_event('request', request_id=request_id, path=getattr(route, 'path', 'unmatched'), method=request.method,
                  status=status, ms=round((time.perf_counter()-start)*1000, 2))

@app.get('/health')
def health():
    return {'status': 'ok'}

@app.get('/ready')
def ready():
    if not redis_healthy():
        return JSONResponse(status_code=503, content={'status': 'not ready'})
    return {'status': 'ready'}

@app.post('/ask')
def ask(body: AskRequest, key: str = Depends(verify_api_key)):
    check_rate_limit(key)
    input_tokens = estimate_tokens(body.question)
    reservation = check_budget(input_tokens, MAX_OUTPUT_TOKENS)
    try:
        answer = llm_ask(body.question)
    except Exception:
        cancel_reservation(reservation)
        raise HTTPException(status_code=502, detail='Mock LLM unavailable')
    output_tokens = estimate_tokens(answer)
    cost = record_cost(reservation, input_tokens, output_tokens)
    return {'question': body.question, 'answer': answer,
            'usage': {'input_tokens': input_tokens, 'output_tokens': output_tokens, 'cost_usd': cost}}
