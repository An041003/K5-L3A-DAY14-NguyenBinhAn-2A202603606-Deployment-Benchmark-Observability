# Benchmark & Observability Report — Day 14

Họ tên: NguyenBinhAn · MSSV: 2A202603606  
Ngày chạy: 2026-11-25  
Môi trường đo (OS, CPU/RAM, Python, Docker): Windows 11, Intel Core i7-11850H @ 2.50GHz (16 logical cores), 15.20 GB RAM, Python 3.12.10 (`.venv`), Docker Desktop 29.4.3 / Docker Compose v5.1.3

Chỉ các bảng giữa marker AUTO được script làm mới. Các phần nhận xét và chứng cứ thủ công bên ngoài marker được giữ nguyên. CP7: eval tắt lỗi upstream ngẫu nhiên (`MOCK_ERROR_RATE=0`) để cô lập chất lượng; performance giữ `MOCK_ERROR_RATE=0.01`, `MOCK_SLOW_RATE=0.03` (mặc định, trừ bảng 2.2 thay đổi `0 / 0.03 / 0.1`), `LLM_MODEL=mock-llm-small`, 300 requests/mức. CP8: chạy trên stack `-p k5-day14-observability` với cấu hình baseline đồng nhất (`v2`, `mock-llm-small`, `MOCK_LATENCY_MS=120`, `MOCK_SLOW_RATE=0.03`, `MOCK_ERROR_RATE=0.01`).

## 1. SLO của agent

| SLI | SLO local | Lý do |
|---|---|---|
| p95 latency `/ask` | ≤500 ms | Phản hồi tương tác tốt cho người dùng |
| Error rate `/ask` | ≤2% | Giới hạn lỗi upstream chấp nhận được (mock mặc định 1%) |
| Accuracy | 100% (23/23), không regression | Golden dataset đầy đủ sau khi sửa KB |

Production alert không đồng nhất với SLO local: error >5% trong 1m; p95 >1s trong 2m; instance down trong 30s; cost burn >$2/h trong 2m. Các ngưỡng lấy từ `alert_rules.yml` (giữ nguyên không chỉnh sửa).

## 2. Benchmark hiệu năng (develop)
### 2.1 Concurrency vs latency
<!-- BEGIN AUTO:LOAD -->
| Concurrency | RPS | p50 ms | p95 ms | p99 ms | Error rate | SLO |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 4.19 | 202.0 | 232.2 | 1719.5 | 1.67% | PASS |
| 10 | 40.16 | 190.3 | 235.5 | 1691.2 | 0.33% | PASS |
| 50 | 103.47 | 194.1 | 269.0 | 1716.1 | 1.00% | PASS |
| 100 | 71.39 | 337.3 | 3432.4 | 3914.3 | 1.00% | FAIL |
<!-- END AUTO:LOAD -->

**Nhận xét từ số đo thực:**
- RPS **không tăng tuyến tính** theo concurrency: từ `c=1` (4.19 req/s) lên `c=10` (40.16 req/s, ~9.6x) vẫn gần tuyến tính, nhưng lên `c=50` chỉ đạt 103.47 req/s (~2.58x so với `c=10`), và tại **`c=100` RPS tụt xuống 71.39 req/s** trong khi **p95 tăng vọt từ 269.0 ms lên 3,432.4 ms** (>6.8x ngưỡng SLO 500 ms) dẫn tới **SLO FAIL** (dù error rate vẫn giữ ở 1.00% ≤ 2%).
- Nguyên nhân: agent `develop/app.py` chạy single-process Uvicorn trên local, khi concurrency chạm ngưỡng bão hòa (giữa 50 và 100 kết nối đồng thời), hàng đợi socket/event loop và contention ở client/server làm tăng mạnh queueing delay (p50 tăng từ ~194 ms lên 337.3 ms, p95/p99 vượt 3.4–3.9 giây).

### 2.2 Tail latency
<!-- BEGIN AUTO:TAIL -->
| Slow rate | avg ms | p95 ms | p99 ms |
| --- | --- | --- | --- |
| 0 | 187.9 | 228.7 | 235.4 |
| 0.03 | 258.6 | 248.3 | 1714.3 |
| 0.1 | 368.8 | 1702.0 | 1725.2 |
<!-- END AUTO:TAIL -->

**Nhận xét từ số đo thực:**
- **p99 và p95 là các chỉ số nhạy nhất** với request chậm:
  - Khi `MOCK_SLOW_RATE` tăng từ `0` → `0.03` (3% request chậm), `avg` chỉ tăng từ 187.9 ms lên 258.6 ms (+37.6%) và `p95` vẫn ở 248.3 ms, nhưng **`p99` nhảy vọt hơn 7.2 lần** từ 235.4 ms lên **1,714.3 ms**.
  - Khi tăng lên `0.1` (10% request chậm), `avg` mới là **368.8 ms** (vẫn nằm dưới ngưỡng 500 ms!), nhưng cả **`p95` (1,702.0 ms)** lẫn **`p99` (1,725.2 ms)** đều vượt xa SLO (>3.4x ngưỡng 500 ms).
- Do đó, đặt SLO theo `average` che giấu hoàn toàn trải nghiệm xấu của nhóm 5–10% người dùng chịu tail latency; bắt buộc đặt SLO theo `p95`/`p99`.

## 3. Benchmark chất lượng (develop)
<!-- BEGIN AUTO:QUALITY -->
| Version | Accuracy | Avg tokens | Cost USD | Cost/correct | Gate | Regression |
| --- | --- | --- | --- | --- | --- | --- |
| eval_v1 | 4.35% (1/23) | 57.0 | 0.000403 | 0.00040335 | FAIL | 0 |
| eval_v2 | 91.30% (21/23) | 109.0 | 0.00076 | 3.619e-05 | PASS | 0 |
| eval_v2_fixed | 100.00% (23/23) | 114.1 | 0.000794 | 3.453e-05 | PASS | 0 |
<!-- END AUTO:QUALITY -->

### Những câu v2 sai ban đầu
<!-- BEGIN AUTO:FAILURES -->
| ID fail ban đầu | Thiếu keyword | Sau sửa |
| --- | --- | --- |
| security-02 | token, hết hạn, chữ ký | PASS |
| scaling-03 | cpu, memory, custom metrics | PASS |
<!-- END AUTO:FAILURES -->

- **Hướng sửa:** Bổ sung 2 tài liệu về **JWT** (token có chữ ký, claims, thời điểm hết hạn) và **Kubernetes HPA** (CPU, memory, custom metrics) vào `KNOWLEDGE_BASE` trong `06-lab-complete/benchmark-observability/develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`), giữ nguyên hoàn toàn `golden_dataset.jsonl` và `run_eval.py`.
- **Phân tích trade-off chất lượng / chi phí / latency:**
  - So với `v1` (p50=172.1 ms, p95=202.7 ms, avg=57.0 tokens, total cost=\$0.000403, accuracy 4.35%), `v2` thêm bước retrieval nên tăng nhẹ latency (+28.0 ms ở p95 → 230.7 ms) và tăng gần gấp đôi tổng token/cost (109.0 tokens, \$0.00076, +88.6%). Tuy nhiên **accuracy tăng +87.0 điểm %** (1/23 → 21/23), khiến **`cost / câu đúng` giảm hơn 11 lần** (từ \$0.00040335 xuống \$0.00003619).
  - Sau khi vá KB (`eval_v2_fixed`), p95 gần như không đổi (231.4 ms, +0.7 ms), tổng cost tăng nhẹ (\$0.000760 → \$0.000794, +4.5%), nhưng đạt **100% (23/23)** với **0 regression**, kéo `cost / câu đúng` xuống **\$0.00003453**.
- **CI quality gate:** Đã cấu hình [.github/workflows/day14-quality.yml](.github/workflows/day14-quality.yml) chạy `eval/run_eval.py --min-accuracy 1.0 --baseline ../../../reports/eval_v2.json`. Script trả về exit code `1` nếu accuracy dưới ngưỡng hoặc phát sinh regression; kết hợp Branch Protection (required status check) sẽ tự động chặn merge PR lỗi.

## 4. Observability stack (production)
### 4.1 Screenshot
- [x] [Grafana dashboard có tải](screenshots/grafana-dashboard.png) — chụp dưới tải thực tế, hiển thị đầy đủ Golden Signals (`Traffic 10.2 req/s`, `Error rate 0.18%`, `Latency p95 291.06 ms`, `Instances up 2`, `LLM cost (1h) $0.5397`), biểu đồ Latency p50/p95/p99, Requests/s theo status code & instance, Tokens/s, Cost burn rate và Retrieval hit ratio 100%.
- [x] [Jaeger trace chậm](screenshots/jaeger-slow-trace.png) — `trace_id: 5953a678ce235877993e3a89c205ece9` (`Duration 2.0s`), mở rộng span chậm nhất `chat mock-llm-small` (`1.7s`, Input 95 / Output 55 tokens).
- [x] [Jaeger trace lỗi có exception](screenshots/jaeger-error-trace.png) — `trace_id: 551ab2a0cb978f7c74dc59b1257bca86` (`503`, `883ms`), mở tab `Details` → `Events (1)` thấy rõ `exception (880.76ms): Upstream LLM error: 503 Service Unavailable (mock)`.
- [x] [Prometheus: ≥2 alert cùng firing](screenshots/prometheus-alert-firing.png) — hiển thị đồng thời **3 alerts đang FIRING** (`AgentHighErrorRate`, `AgentHighLatencyP95`, `LLMCostBurnRateHigh`).

### 4.2 Thí nghiệm phá hệ thống
Tải nền liên tục 35 Locust users trên 2 agent replicas (`-p k5-day14-observability`), giữ nguyên toàn bộ ngưỡng & `for` trong `prometheus/alert_rules.yml`:

| Case | Thay đổi | Alert kỳ vọng | Alert thực tế | Thời gian từ gây lỗi → vượt ngưỡng / firing / recovery | Panel phản ánh rõ nhất |
|---|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`) | `AgentHighErrorRate` (**19.03%** > 5%) | Vượt ngưỡng `+33.6s` → **FIRING `+93.9s`** · Clear sau khôi phục: `40.1s` | Error rate, Requests/s theo status code (503), LLM calls theo kết quả |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`for: 2m`) | `AgentHighLatencyP95` (**1.915s** > 1s) | Vượt ngưỡng `+27.5s` → **FIRING `+147.9s`** · Clear sau khôi phục: `48.1s` | Latency p95, Latency `/ask` p50/p95/p99, LLM latency p95 theo model |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`for: 2m`) | `LLMCostBurnRateHigh` (**\$18.04/giờ** > \$2/h) | Vượt ngưỡng `+27.5s` (\$2.63/h) → **FIRING `+147.9s`** | Cost burn rate (USD/giờ), LLM cost (1h), bảng Phiên bản đang chạy |
| D | `docker pause` 1 instance (`eebf989ab26d`) | `AgentInstanceDown` (`for: 30s`) | `AgentInstanceDown` (`172.21.0.8:8000`) | Vượt ngưỡng `+9.2s` → **FIRING `+39.2s`** · Clear sau `unpause`: `4.0s` | Instances up (giảm 2 → 1), Requests/s theo instance |
| E | `AGENT_VERSION=v1` | Không có alert chất lượng | **0 alert firing (`[]`)** dù `POST /ask` trả câu trả lời thiếu RAG | Theo dõi `60s`: toàn bộ hạ tầng vẫn xanh (`200 OK`) | Bảng Phiên bản đang chạy (`v1`), Retrieval hit ratio giảm về 0% |
| A+B | `MOCK_ERROR_RATE=0.2` & `MOCK_SLOW_RATE=0.3` đồng thời | ≥2 alerts firing | **`AgentHighErrorRate` (22.03%) + `AgentHighLatencyP95` (1.9s)** (+ `LLMCostBurnRateHigh` dư âm cửa sổ `[5m]` từ case C) | `AgentHighErrorRate`: vượt ngưỡng `+31.9s` → **FIRING `+89.1s`**; `AgentHighLatencyP95`: vượt ngưỡng `+31.9s` → **FIRING `+149.4s`** | Prometheus `/alerts` (chụp [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)) |

**Phân tích bổ sung:**
- **Case E (suy giảm chất lượng thầm lặng):** Khi rollback nhầm sang `v1`, agent vẫn trả `HTTP 200` nhanh (`Container là cách đóng gói app để chạy ở mọi nơi...` dù câu hỏi hỏi về multi-stage Dockerfile) nên không có bất kỳ alert hạ tầng nào kích hoạt. Trong production phải phát hiện bằng offline golden eval (CI quality gate), online quality sampling (LLM-as-a-judge / heuristic) và theo dõi metric đặc thù của RAG như `Retrieval hit ratio` kết hợp phản hồi người dùng.
- **Case D (`pause` vs `stop`):** `docker pause` đóng băng process nhưng giữ nguyên container và DNS record nên Prometheus vẫn scrape IP cũ, gặp timeout và chuyển `up{job="agent"} == 0` sau 30s (`AgentInstanceDown`). Ngược lại `docker stop` có thể xóa container khỏi DNS discovery khiến target biến mất thay vì `up == 0` — cần thêm alert theo tổng số replica kỳ vọng (`count(up{job="agent"} == 1) < 2`).
- **Gateway timeout (504):** Nếu Nginx timeout trước khi agent trả response, agent có thể không ghi nhận status 504; cần bổ sung metric từ Nginx/API gateway và synthetic probe từ bên ngoài.

### 4.3 Debug bằng trace

**1. Trace chậm (`status=200`):**
- `trace_id`: `5953a678ce235877993e3a89c205ece9` (`request_id`: `e95412a72514`, `instance`: `430e428e4c7e`)
- Tổng thời gian (`POST /ask`): **1,985.28 ms**
- Chi tiết các span:
  - `agent.run`: 1,715.13 ms (86.4%)
  - `agent.retrieve_context`: 21.48 ms (1.1%, `retrieval.documents=1`)
  - **Span chậm nhất (`chat mock-llm-small`)**: **1,693.40 ms** (**85.3%** tổng thời gian request; `input_tokens=95`, `output_tokens=55`, `llm.cost_usd=$0.00004725`)
- Dòng JSON log tương ứng (trích từ `docker compose -p k5-day14-observability logs agent`, khớp chính xác `trace_id`):
```json
{"ts": "2026-11-25T09:19:38.225352+00:00", "level": "INFO", "service": "observable-agent", "instance": "430e428e4c7e", "event": "llm_call", "trace_id": "5953a678ce235877993e3a89c205ece9", "span_id": "7220077f1da3a701", "request_id": "e95412a72514", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1693.0}
{"ts": "2026-11-25T09:19:38.225888+00:00", "level": "INFO", "service": "observable-agent", "instance": "430e428e4c7e", "event": "http_request", "trace_id": "5953a678ce235877993e3a89c205ece9", "span_id": "7220077f1da3a701", "request_id": "e95412a72514", "method": "POST", "route": "/ask", "status": 200, "ms": 1984.6}
```

**2. Trace lỗi (`status=503`):**
- `trace_id`: `551ab2a0cb978f7c74dc59b1257bca86` (`request_id`: `9898fda5c165`, `instance`: `1b4162a0d98d`)
- Tổng thời gian (`POST /ask`): **882.81 ms** (`http.status_code=503`, `status.code=2` ERROR)
- Span & event `exception`: **`chat mock-llm-small`** (`863.40 ms`, `error.type=upstream_unavailable`) ghi nhận event `exception` tại `880.76 ms` với `exception.type: utils.mock_llm.LLMError`, `exception.message: Upstream LLM error: 503 Service Unavailable (mock)` tại `/app/utils/mock_llm.py:204`.
- Dòng JSON log tương ứng:
```json
{"ts": "2026-11-25T09:22:10.658264+00:00", "level": "INFO", "service": "observable-agent", "instance": "1b4162a0d98d", "event": "llm_error", "trace_id": "551ab2a0cb978f7c74dc59b1257bca86", "span_id": "221699381926e918", "request_id": "9898fda5c165", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts": "2026-11-25T09:22:10.658790+00:00", "level": "INFO", "service": "observable-agent", "instance": "1b4162a0d98d", "event": "http_request", "trace_id": "551ab2a0cb978f7c74dc59b1257bca86", "span_id": "221699381926e918", "request_id": "9898fda5c165", "method": "POST", "route": "/ask", "status": 503, "ms": 882.0}
```

### 4.4 Incident analysis (bổ sung theo slide)
Quy trình xử lý thực tế trong các thí nghiệm A–D: **Detect** (Prometheus alert firing) → **Triage** (Grafana xác nhận panel `Error rate` / `Latency p95` / `Cost burn rate` / `Instances up`) → **Correlate** (từ trace chậm/lỗi trên Jaeger tra ngược `trace_id` sang JSON log container) → **Root Cause** (xác định nút thắt nằm ở span `chat mock-llm-small` chiếm 85.3% latency hoặc lỗi `LLMError 503` từ upstream, không phải ở retrieval `21.48 ms`) → **Mitigate & Verify** (khôi phục cấu hình baseline hoặc `docker unpause`, theo dõi alert chuyển về `inactive`).
- **MTTD đo thực tế** (từ thời điểm gây lỗi đến lúc alert firing — luôn lớn hơn giá trị `for` do cộng thêm thời gian recreate/scrape/cửa sổ `rate[1m]`):
  - `AgentInstanceDown` (`for: 30s`): **39.2s**
  - `AgentHighErrorRate` (`for: 1m`): **89.1s – 93.9s**
  - `AgentHighLatencyP95` (`for: 2m`): **147.9s – 149.4s**
  - `LLMCostBurnRateHigh` (`for: 2m`): **147.9s**
- **Thời gian hồi phục alert sau khôi phục (clear time):** `4.0s` (Case D), `40.1s` (Case A), `48.1s` (Case B).

## 5. Benchmark scaling (Locust headless, 100 users, 2 phút)
<!-- BEGIN AUTO:SCALING -->
| Instances | RPS | p50 ms | p95 ms | p99 ms | Failures |
| --- | --- | --- | --- | --- | --- |
| 1 | 65.84389896063587 | 190 | 270 | 1700 | 77 |
| 3 | 65.91167222092066 | 190 | 220 | 1700 | 77 |
<!-- END AUTO:SCALING -->

**Nhận xét từ CSV thực (`scale_1_stats.csv` vs `scale_3_stats.csv`):**
- Cả 2 lần đo chạy cùng cấu hình baseline (`v2`, `mock-llm-small`, `MOCK_SLOW_RATE=0.03`, `MOCK_ERROR_RATE=0.01`, 100 users, spawn 10/s, 2 phút, dùng `--no-deps` để giữ đúng 1 và 3 instances):
  - **Cải thiện p95:** Scale từ 1 → 3 instances giúp **p95 Aggregated giảm từ 270 ms → 220 ms (-18.5%)** (`POST /ask` giảm từ **280 ms → 230 ms**, `GET /health` giảm từ **19 ms → 6 ms**) do phân tải kết nối và giảm CPU/event-loop queueing giữa các replica (tải mỗi instance giảm từ ~60 req/s xuống ~20 req/s).
  - **Vì sao RPS (~65.8 vs ~65.9 req/s), p50 (190 ms) và p99 (1700 ms) gần như không đổi:**
    1. Trong `locustfile.py`, 100 virtual users có thời gian nghỉ (`wait_time`) giữa các lượt gửi nên tổng lưu lượng tối đa phía client đạt ~66 RPS, chưa làm bão hòa hoàn toàn 1 instance FastAPI bất đồng bộ.
    2. **Nút thắt latency nằm ở upstream LLM call** (xác nhận qua Jaeger trace: `chat mock-llm-small` chiếm ~85% thời gian, và 3% request chậm cộng thêm `1,500 ms` tạo nên `p99 = 1,700 ms`). Scale ngang tăng capacity xử lý đồng thời và giảm queueing, nhưng **không thể rút ngắn thời gian xử lý của một lời gọi LLM đơn lẻ**; muốn giảm p99 phải tối ưu tầng LLM (timeout + retry/hedging, streaming, model nhẹ hơn, semantic cache).
  - **Failures (77/7,869 ≈ 0.98% ở cả hai mức):** Toàn bộ 77 lỗi là `HTTP 503` do `MOCK_ERROR_RATE=0.01` từ upstream giả lập, không có lỗi kết nối hay timeout từ Nginx.

## 6. Kết luận
Ba điều rút ra từ toàn bộ thực nghiệm CP7 & CP8:
1. **Hiệu năng & Tail latency:** Throughput không tăng tuyến tính khi vượt điểm bão hòa (`c=50` đạt 103.47 RPS nhưng `c=100` tụt còn 71.39 RPS và p95 vọt lên 3,432.4 ms → SLO FAIL). Ở `MOCK_SLOW_RATE=0.1`, `avg` vẫn là 368.8 ms (< 500 ms) trong khi `p95` đã là 1,702.0 ms; và khi scale 1→3 instances, p95 cải thiện (-18.5%) nhưng p99 vẫn cố định ở 1,700 ms do nút thắt nằm ở upstream LLM.
2. **Chất lượng, regression & chi phí:** Thêm retrieval (`v2`) và vá đúng 2 lỗ hổng KB (`security-02`, `scaling-03`) nâng accuracy từ 4.35% → 91.30% → 100.00% (23/23, 0 regression) đồng thời giảm `cost / câu đúng` hơn 11 lần (\$0.00040335 → \$0.00003453). Quality gate tự động dựa trên exit code là chốt chặn bắt buộc vì lỗi chất lượng (Case E) hoàn toàn không làm kích hoạt alert hạ tầng.
3. **Observability & Incident response:** Kết hợp Metrics (Prometheus/Grafana), Traces (Jaeger) và Structured JSON Logs nối nhau bằng `trace_id` cho phép khoanh vùng nhanh nguyên nhân gốc trong vài giây (ví dụ `trace_id 5953a678ce235877993e3a89c205ece9` chỉ rõ `chat mock-llm-small` chiếm 85.3% thời gian, và `551ab2a0cb978f7c74dc59b1257bca86` trỏ thẳng tới `LLMError` dòng 204). Thời gian phát hiện thực tế (MTTD: 39s–149s) luôn gồm scrape interval + cửa sổ tính rate + ngưỡng `for`.

Hướng nâng cao khi đưa lên production thật: kết hợp đủ 4 trụ cột (Metrics, Logs, Traces và Continuous/Online Eval — hiện lab mới triển khai offline golden eval), bổ sung metric gateway 5xx, queue/in-flight saturation, retrieval hit ratio alert, model/version drift, feedback sampling, không log prompt/response/API key/PII thô, và gắn runbook/owner/severity/multi-window burn-rate alert.
