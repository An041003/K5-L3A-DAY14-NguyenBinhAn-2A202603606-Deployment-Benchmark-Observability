# Day 14 Lab — Mission Answers

> Đã thực nghiệm trên máy local (Windows 11 + Docker Desktop 29.4.3 / Compose v5.1.3, Python 3.12.10, và môi trường Linux POSIX + Docker cho official grader CP5). Mục Part 3 public URL đang chờ triển khai cloud ở CP6.

## Part 1 — Localhost vs Production

### 1.1 Anti-patterns tìm thấy trong `01-localhost-vs-production/develop/app.py`
1. **Hardcode secrets trong source code** (dòng 17–18): `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` → lộ credentials ngay nếu push lên Git.
2. **In secret và dữ liệu người dùng bằng `print()`** (dòng 33–38): `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` → lộ API key và prompt/response ra stdout, không có cấu trúc JSON để lọc/tìm kiếm.
3. **Hardcode cấu hình không quản lý theo môi trường** (dòng 21–22): `DEBUG = True`, `MAX_TOKENS = 500` cố định trong source.
4. **Không có health/readiness endpoints** (dòng 42–43): thiếu `GET /health` và `GET /ready` nên orchestrator/load balancer không phát hiện được container treo hoặc chưa sẵn sàng.
5. **Cố định `host="localhost"`, `port=8000` và `reload=True`** (dòng 49–54): chỉ truy cập được từ loopback trong container, không nhận biến `PORT` do nền tảng cloud cấp, và bật hot-reload gây tốn tài nguyên/rủi ro trên production.
6. **Không có cơ chế graceful shutdown / lifespan** để dọn dẹp tài nguyên và chờ in-flight requests hoàn tất khi nhận `SIGTERM`.
7. **Nhận input qua query parameter** (`POST /ask?question=...`) thay vì JSON request body có validation chặt chẽ.

**Đối chiếu với `01-localhost-vs-production/production/`:**
- `production/config.py` đọc toàn bộ cấu hình từ biến môi trường (`os.getenv`) và **fail-fast** khi thiếu secret trong production (kiểm chứng thực tế khi chạy `ENVIRONMENT=production` chưa đặt `AGENT_API_KEY` → ném `ValueError: AGENT_API_KEY must be set in production!`).
- `production/app.py` dùng `lifespan` cho startup/shutdown (dòng 40–67), log JSON không chứa secret (dòng 28–31, 111–122), có `GET /health` (dòng 135) và `GET /ready`, nhận JSON body cho `POST /ask`.

### 1.2 Kết quả chạy thực tế (Develop & Production)

**Bản Develop** (`01-localhost-vs-production/develop/app.py` — nhận query parameter):
```http
POST /ask?question=Hello
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

**Bản Production** (`01-localhost-vs-production/production/app.py` với `ENVIRONMENT=production` và `AGENT_API_KEY` demo):
```http
GET /health -> HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":0.5,"version":"1.0.0","environment":"production","timestamp":"2026-11-25T08:17:05.493390+00:00"}

GET /ready -> HTTP/1.1 200 OK
{"ready":true}

POST /ask (JSON body {"question":"Hello"}) -> HTTP/1.1 200 OK
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}
```

### 1.3 Bảng so sánh Develop vs Production

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Vì sao quan trọng? |
|---|---|---|---|
| Config & Secrets | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `MAX_TOKENS` | Đọc từ env vars qua `Settings` + `validate()` fail-fast | Cùng một image chạy được ở dev/staging/prod, tránh lộ secret trong Git |
| Health / Readiness | Không có | Có `GET /health` (liveness) và `GET /ready` (readiness) | Phân biệt process còn sống vs sẵn sàng nhận traffic để tự restart/route đúng |
| Logging | `print()` tự do, in cả API key và nội dung | Structured JSON logging, chỉ log metadata (`question_length`, `response_length`) | Dễ truy vấn trong log aggregator (Loki/Datadog) và không lộ bí mật/PII |
| Shutdown | Không có lifecycle cleanup | `lifespan` cập nhật `is_ready = False`, drain in-flight request | Tránh cắt ngang request người dùng khi deploy/restart |
| Host / Port | `localhost:8000` cố định | `0.0.0.0` + biến môi trường `PORT` | Container nhận được traffic từ ngoài và tương thích Railway/Render/Cloud Run |
| Debug / Reload | `DEBUG = True`, `reload = True` | Tắt reload mặc định, điều khiển `debug` qua env | Tránh overhead theo dõi file và tránh lộ thông tin nội bộ |

---

## Part 2 — Docker

### 2.1 Câu hỏi Dockerfile (`02-docker/develop/Dockerfile`)
1. **Base image:** `python:3.11` (bản full Debian gồm đầy đủ compiler và công cụ build, dung lượng lớn).
2. **Working directory:** `/app` (`WORKDIR /app`).
3. **Vì sao `COPY requirements.txt` trước `COPY . .`:** Tận dụng Docker layer cache — khi chỉ sửa source code ứng dụng mà không đổi `requirements.txt`, Docker tái sử dụng layer `pip install`, giảm mạnh thời gian build lại.
4. **`CMD` vs `ENTRYPOINT`:** `ENTRYPOINT` cố định executable chính của container (ít bị ghi đè), còn `CMD` cung cấp lệnh mặc định hoặc tham số mặc định cho `ENTRYPOINT` và dễ override khi chạy `docker run <image> <cmd>`.

### 2.2–2.3 Build, test container và so sánh kích thước image

Build từ gốc repo:
- `docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .`
- `docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .`

Test container `my-agent:develop`:
```http
POST /ask?question=Docker -> HTTP/1.1 200 OK
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

So sánh kích thước đo thực tế trên máy:
- **Theo `docker images` (disk/unpacked size):**
  - Develop (`my-agent:develop`): **1.67 GB** (~1,670 MB)
  - Production (`my-agent:advanced`): **240 MB**
  - Chênh lệch giảm: **~85.63%**
- **Theo `docker image inspect --format '{{.Size}}'`:**
  - Develop: **426,320,081 bytes (406.57 MiB)**
  - Production: **57,408,971 bytes (54.75 MiB)**
  - Chênh lệch giảm: **86.53%**

**Vì sao multi-stage giảm dung lượng mạnh:** Stage `builder` cài đặt dependencies (và build wheels nếu có gói C), còn stage `runtime` dùng base `python:3.11-slim`, chỉ `COPY --from=builder` các package đã cài sang và chạy bằng user non-root `appuser` — loại bỏ toàn bộ build toolchain, pip cache và lớp thừa, vừa giảm >85% kích thước vừa thu hẹp bề mặt tấn công.

### 2.4 Docker Compose stack (`02-docker/production`, project `k5-day14-docker`)

```mermaid
graph LR
  Client --> Nginx["Nginx :80 (Reverse Proxy + Rate Limit)"]
  Nginx --> Agent["Agent :8000 (FastAPI)"]
  Agent --> Redis["Redis :6379 (Session/Cache)"]
  Agent --> Qdrant["Qdrant :6333 (Vector DB)"]
```

- Tạo `.env.local` trống cho mock LLM, chạy `docker compose -p k5-day14-docker up -d --build`.
- Trạng thái `docker compose -p k5-day14-docker ps`: đủ 4 service `k5-day14-docker-nginx-1` (port 80/443), `k5-day14-docker-agent-1`, `k5-day14-docker-redis-1` (healthy), `k5-day14-docker-qdrant-1` (healthy).
- Kiểm tra qua Nginx (`http://127.0.0.1:80/health`):
```http
HTTP/1.1 200 OK
Server: nginx
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":1.1,"version":"2.0.0","timestamp":"2026-11-25T08:13:54.341460"}
```
- Sau khi kiểm thử đã dọn sạch bằng `docker compose -p k5-day14-docker down -v`.

---

## Part 3 — Cloud Deployment

### 3.1 Triển khai agent Part 6 trên nền tảng chính (Railway)
- **URL public:** PENDING — xem [DEPLOYMENT.md](DEPLOYMENT.md) (cần đăng nhập tài khoản Railway để deploy `06-lab-complete/` kèm Redis service và xác minh 4 lệnh CP6).
- **Screenshots:** `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png` (PENDING sau bước deploy).

### 3.2 So sánh `railway.toml` vs `render.yaml`
- **`railway.toml`** (TOML, gọn nhẹ): chỉ khai báo phần build (`builder = "DOCKERFILE"`) và chính sách deploy (`healthcheckPath = "/health"`, `healthcheckTimeout = 60`, `restartPolicyType = "ON_FAILURE"`, `restartPolicyMaxRetries = 3`). Biến môi trường và dịch vụ Redis được cấu hình trên dashboard Railway (tham chiếu private `REDIS_URL` giữa các service trong cùng project).
- **`render.yaml`** (YAML Blueprint — Infrastructure as Code): khai báo đầy đủ danh sách services (`type: web`, `runtime: docker`, `rootDir: 06-lab-complete`, `dockerfilePath: ./Dockerfile`, `healthCheckPath: /health`) kèm danh sách `envVars` ngay trong repo. Điểm quan trọng là **không ghi thẳng giá trị secret**: dùng `generateValue: true` cho `AGENT_API_KEY` (Render tự sinh key ngẫu nhiên) và `sync: false` cho `REDIS_URL` (người vận hành nhập giá trị trên dashboard).
- **Điểm chung:** Cả hai đều inject biến `PORT` động vào container, kiểm tra liveness qua `/health`, và tách hoàn toàn secret khỏi mã nguồn.

### 3.3 Cloud Run — phân tích pipeline CI/CD (`03-cloud-deployment/production-cloud-run/`)
1. `cloudbuild.yaml` chạy bước kiểm thử (`pip install -r requirements.txt && pytest`) trước để chặn pipeline ngay nếu test thất bại.
2. Bước tiếp theo build Docker image, gắn đồng thời 2 tag `$COMMIT_SHA` (bất biến theo commit) và `latest`, rồi push lên Container Registry/Artifact Registry.
3. Bước cuối gọi `gcloud run deploy` triển khai image theo `$COMMIT_SHA` lên Cloud Run khu vực `asia-southeast1`, cấu hình auto-scaling (`min-instances`, `max-instances`), tài nguyên CPU/RAM, timeout và gắn secrets từ Secret Manager.
4. `service.yaml` định nghĩa đặc tả Knative/Cloud Run Service gồm `containerConcurrency`, scaling annotations, biến môi trường, tham chiếu secret, `livenessProbe` (`/health`) và `startupProbe` (`/ready`).

---

## Part 4 — API Security

### 4.1–4.3 Kết quả kiểm thử thực tế (`04-api-gateway/`)

**1. API Key Authentication (`04-api-gateway/develop`, `AGENT_API_KEY=secret-key-123`):**
- Không có header `X-API-Key` → **401 Unauthorized**:
```http
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```
- Có header `X-API-Key` hợp lệ → **200 OK**:
```http
HTTP/1.1 200 OK
content-type: application/json

{"question":"hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

**2. JWT + Rate Limiting (`04-api-gateway/production`, tài khoản demo `student` / `demo123`):**
- Đăng nhập lấy JWT tại `POST /auth/token` → `200 OK` (đã che token: `<REDACTED_JWT>`).
- Gọi `POST /ask` không có token → **401 Unauthorized**:
```http
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
content-type: application/json

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```
- Gọi vòng lặp 12 requests với `Authorization: Bearer <REDACTED_JWT>`:
  - Request 1..10: **HTTP/1.1 200 OK** (request 1 trả về `{"usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}`, giảm dần về 0).
  - Request 11 & 12: **HTTP/1.1 429 Too Many Requests**:
```http
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795594627
retry-after: 59
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

**Giải thích xoay vòng & so sánh:**
- Khi API key bị lộ, revoke/đổi `AGENT_API_KEY` trong secret manager/platform env và redeploy, không bao giờ log key ra console.
- Trong `04-api-gateway/production`, rate limiter lưu sliding window bằng `deque` trong RAM của từng process nên không dùng chung giữa nhiều instance; còn trong Part 6 (`06-lab-complete/app/rate_limiter.py`), state được lưu bằng **Redis ZSET + Lua script atomic** theo SHA-256 hash của API key và thời gian `redis.call('TIME')`, nên nhiều worker/restart đều dùng chung chính xác một cửa sổ giới hạn.

### 4.4 Cost Guard
- **Vì sao cần cả Rate Limit lẫn Cost Guard:** Rate limit chặn tốc độ gửi request (chống spam/DDoS), nhưng một số ít request dài hoặc dùng model đắt vẫn có thể gây đội chi phí LLM; Cost Guard giới hạn trực tiếp ngân sách (USD) theo chu kỳ.
- **Khác biệt giữa ví dụ Part 4 và Part 6:** Ví dụ Part 4 theo dõi budget theo từng user trong RAM; bản Part 6 (`06-lab-complete/app/cost_guard.py`) quản lý ngân sách **global theo ngày/tháng UTC trong Redis** bằng đơn vị số nguyên **nanodollar** (tránh sai số dấu phẩy động), dùng 2 bước Lua atomic:
  1. `check_budget` **reserve trước** mức chi phí tối đa có thể phát sinh trước khi gọi LLM; nếu vượt `DAILY_BUDGET_USD` hoặc `MONTHLY_BUDGET_USD` → trả **HTTP 402 Payment Required** (nếu Redis mất kết nối → fail-closed **HTTP 503**).
  2. `record_cost` **settle lại** đúng chi phí thực tế (`input_tokens * 0.00015 / 1000 + output_tokens * 0.0006 / 1000`) sau khi nhận câu trả lời; nếu LLM lỗi thì `cancel_reservation` hoàn trả phần đã reserve.

---

## Part 5 — Scaling & Reliability

### 5.1–5.3 Health/Readiness, Graceful Shutdown & Stateless
- **Liveness (`/health`) vs Readiness (`/ready`):** `/health` luôn trả `200` khi process còn sống (kể cả khi Redis tạm mất kết nối, tránh restart loop vô ích). `/ready` ping Redis — trả `200` khi sẵn sàng và `503` khi Redis down để load balancer tạm ngừng điều hướng traffic tới instance lỗi.
- **Graceful Shutdown:** Dockerfile chạy Uvicorn bằng `sh -c "exec uvicorn ..."` để Uvicorn là PID 1 nhận trực tiếp `SIGTERM`, tự drain toàn bộ in-flight requests trước khi gọi FastAPI `lifespan` đóng kết nối Redis và thoát với exit code `0`.
- **Stateless:** Nếu lưu conversation history hoặc rate limit trong RAM, khi scale nhiều instance phía sau load balancer thì mỗi request rơi vào một instance khác nhau sẽ mất ngữ cảnh. Đưa toàn bộ state vào Redis giải quyết triệt để vấn đề này.

### 5.4–5.5 Kết quả thực nghiệm `05-scaling-reliability/production` (`k5-day14-scaling`, scale 3)
- Chạy `docker compose -p k5-day14-scaling up -d --build --scale agent=3` → 3 agent instances (`agent-1`, `agent-2`, `agent-3`), `redis-1` đều `healthy`, `nginx-1` lắng nghe cổng `8080`.
- Kiểm tra probe qua Nginx (`http://127.0.0.1:8080`):
  - `GET /health` → `200 OK`, `X-Served-By: 172.21.0.3:8000`, `{"status":"ok","instance_id":"instance-479d62","storage":"redis","redis_connected":true}`
  - `GET /ready` → `200 OK`, `X-Served-By: 172.21.0.4:8000`, `{"ready":true,"instance":"instance-ca45e0"}`
- Chạy `python test_stateless.py` (5 câu hỏi cùng `Session ID: 6d3cef40-2a67-4354-89c2-e0a6093df728`):
  - Request 1 → `instance-479d62`
  - Request 2 → `instance-a2411a`
  - Request 3 → `instance-ca45e0`
  - Request 4 → `instance-479d62`
  - Request 5 → `instance-a2411a`
  - **Kết quả:** `Instances used: {'instance-a2411a', 'instance-479d62', 'instance-ca45e0'}` · `Total messages: 10` · `✅ Session history preserved across all instances via Redis!`
- Sau khi kiểm thử đã dừng và dọn sạch bằng `docker compose -p k5-day14-scaling down -v`.

---

## Part 6 — Final Project (`06-lab-complete/`)

Đã chạy official grader `python check_production_ready.py` đầy đủ trong môi trường Linux POSIX (`python:3.11-slim` + Docker 29.4.3 engine + container `redis:7-alpine`, không chỉnh sửa script chấm). Toàn bộ log lưu tại [reports/production_ready.txt](reports/production_ready.txt):

- **Docker image:** multi-stage `python:3.11-slim`, user non-root `agent`, kích thước **63 MB** (< 500 MB), `GET /health` → 200.
- **Runtime (2 workers + Redis):** `/health` 200, `/ready` 200 (và 503 khi Redis down trong khi `/health` vẫn 200), thiếu/sai API key → 401, đúng key → 200, vượt rate limit → 429 và **restart agent vẫn 429** (stateless trong Redis), hết budget → 402, 12 dòng JSON log hợp lệ.
- **Graceful shutdown:** SIGTERM khi đang có request → request vẫn trả 200, process thoát `exit code 0`; `docker stop` tắt êm trong **0.7s** (`exit code 0`).

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## Part 7 — Discussion

1. **Dashboard hạ tầng xanh không chứng minh câu trả lời đúng:** Cần kết hợp golden eval offline trong CI, online quality sampling, đánh giá hồi quy (regression gate) và vòng phản hồi người dùng (human feedback).
2. **Pull model của Prometheus vs scale-to-zero:** Mô hình pull giúp quản lý tập trung target và phát hiện ngay instance chết (`up == 0`). Tuy nhiên với serverless/scale-to-zero không có endpoint sống thường trực để scrape, cần chuyển sang push/OTLP metrics hoặc managed observability backend.
3. **High cardinality với nhãn `user_id`:** 100.000 `user_id` nhân chéo với các nhãn khác làm bùng nổ số time series trong Prometheus (tăng vọt RAM và dung lượng TSDB); ID định danh chi tiết nên đưa vào structured logs hoặc trace attributes thay vì Prometheus labels.
4. **Trade-off của trace sampling:** Giảm chi phí băng thông và lưu trữ nhưng dễ bỏ lỡ lỗi hiếm nếu chỉ head-sampling ngẫu nhiên; nên ưu tiên tail-based sampling (giữ 100% trace lỗi và trace chậm, lấy mẫu nhỏ các trace bình thường).
5. **Chọn ngưỡng `for` cho alert:** `for: 0s` dễ gây báo động giả (alert fatigue) khi chỉ có spike ngắn; `for: 30m` phát hiện sự cố quá chậm, đốt cạn error budget. Cần chọn `for` cân bằng giữa độ nhạy và độ ổn định theo SLO và mức độ nghiêm trọng.

Chi tiết số liệu benchmark & observability xem tại [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md).

---

## AI log (RULES.md)

| Lần sử dụng | Hỏi gì | AI trả về gì | Tôi tự sửa và tự kiểm tra thế nào |
|---|---|---|---|
| 1 | Phân tích và hoàn thiện khung Lab 14 từ repo | Gợi ý code Part 6, bản nháp Mission Answers, script benchmark/eval và unit test fixture | PENDING: học viên tự đọc lại, hiểu rõ từng module trong `06-lab-complete/app/` và xác nhận trước khi nộp |
| 2 | Đối chiếu tài liệu cập nhật K5 (`83e677f`) | Danh sách thay đổi CP0–CP8, rubric, tên file nộp và cấu trúc báo cáo | PENDING: học viên tự đối chiếu lại với `RULES.md`, `CHECKPOINTS.md`, `RUBRIC.md`, `SUBMISSION.md` |
| 3 | Đồng bộ gói bài làm vào workspace lab và thực thi kiểm thử/benchmark thực tế (CP1–CP5, CP7, CP8) | Đồng bộ đúng cấu trúc lab, chạy grader `PASS 12/12` (Linux POSIX + Docker), chạy thực nghiệm CP1–CP4 và benchmark/eval CP7 (23/23), cập nhật kết quả thực tế | PENDING: học viên tự kiểm tra lại toàn bộ số liệu, trực tiếp deploy CP6, xem lại các câu trả lời để giải thích được trước Lab Coach trước khi commit/push |
