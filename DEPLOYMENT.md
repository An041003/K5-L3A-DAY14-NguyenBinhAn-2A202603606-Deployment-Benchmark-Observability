# Deployment Information — Day 14

## Public URL
https://k5-l3a-day14-nguyenbinhan-2a202603606.onrender.com

## Platform & Runtime Configuration
- **Platform:** Render
- **Service Type:** Web Service (`06-lab-complete/` — Production Agent Part 6)
- **Instance Type:** Free
- **Region:** Singapore
- **Runtime:** Docker (`06-lab-complete/Dockerfile`, multi-stage `python:3.11-slim`, non-root)
- **Root Directory:** `06-lab-complete`
- **Data Store:** Render Key Value (Redis / Valkey) — kết nối qua `REDIS_URL`, đã xác minh hoạt động qua `GET /ready` → `200 {"status":"ready"}`
- **Deployment Status:** `Deploy succeeded | Live` (commit `1b2fb5b`, duration `59.4s`)

## Environment Variables Configured (chỉ liệt kê tên biến, không lưu secret)
Các biến môi trường được cấu hình trực tiếp trên Render Dashboard (không hardcode trong source code và không commit lên Git):
- `PORT` (Render inject tự động)
- `REDIS_URL` (kết nối tới Render Key Value service)
- `AGENT_API_KEY` (secret xác thực header `X-API-Key`, cấu hình trên Render Dashboard)
- `ENVIRONMENT` (`production`)
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` / `MONTHLY_BUDGET_USD` (`10`)
- `LOG_LEVEL` (`INFO`)

## Test Commands & Results (CP6 — 4 HTTP Checks)

### Lệnh tự kiểm tra an toàn (PowerShell — nhập key ẩn, không in secret)
```powershell
$BASE = "https://k5-l3a-day14-nguyenbinhan-2a202603606.onrender.com"
$env:AGENT_API_KEY = [System.Net.NetworkCredential]::new("", (Read-Host "API Key" -AsSecureString)).Password

curl.exe -sS --max-time 120 -o NUL -w "Health: %{http_code}`n" "$BASE/health"
curl.exe -sS --max-time 120 -o NUL -w "Ready: %{http_code}`n" "$BASE/ready"
curl.exe -sS --max-time 120 -o NUL -w "No key: %{http_code}`n" -X POST "$BASE/ask" -H "Content-Type: application/json" -d '{\"question\":\"Hello\"}'
curl.exe -sS --max-time 120 -o NUL -w "With key: %{http_code}`n" -X POST "$BASE/ask" -H "Content-Type: application/json" -H "X-API-Key: $env:AGENT_API_KEY" -d '{\"question\":\"Hello\"}'

Remove-Item Env:AGENT_API_KEY
```

### Bảng kết quả kiểm thử thực tế (2026-11-25)

| Check | Endpoint | Auth | Expected | Actual | Ghi chú xác minh |
|---|---|---|---|---|---|
| 1 | `GET /health` | Không | `200` | **`200`** | `{"status":"ok"}` (`294.5 ms`, xác nhận cả qua CLI và [screenshots/test.png](screenshots/test.png)) |
| 2 | `GET /ready` | Không | `200` | **`200`** | `{"status":"ready"}` (`322.1 ms` — xác nhận kết nối Render Key Value Redis/Valkey OK) |
| 3 | `POST /ask` | Không | `401` | **`401`** | `{"detail":"Missing or invalid API key"}` (`138.7 ms`) |
| 4 | `POST /ask` | `X-API-Key` | `200` | **`200`** | Xác minh trực tiếp với `AGENT_API_KEY` ẩn trên terminal học viên ([screenshots/test.png](screenshots/test.png)) |

## Known Limitations (Render Free Tier)
- **Cold start (spin down):** Web Service gói Free tự động ngủ khi không có traffic; như thông báo trên Render Dashboard, request đầu tiên sau giai đoạn không hoạt động có thể bị trễ 50 giây trở lên (nên dùng `--max-time 120` khi gọi lần đầu).
- **Redis / Key Value Free không có persistence:** Render Key Value gói Free lưu trữ dữ liệu trong RAM và không bật disk persistence; do đó state của rate limit và bộ đếm chi phí (cost guard) sẽ bị reset nếu Redis service khởi động lại hoặc bảo trì.

## Screenshots
- [Render Deploy succeeded & runtime JSON logs](screenshots/dashboard.png) — hiển thị `Deploy succeeded | Live` (commit `1b2fb5b`, `59.4s`) và log JSON `GET /health 200 OK`
- [Render Web Service overview & Live status](screenshots/running.png) — hiển thị Web Service `Docker / Free`, badge `✓ Live`, Public URL `https://k5-l3a-day14-nguyenbinhan-2a202603606.onrender.com` và sự kiện `Deploy live`
- [Public API 4 HTTP test results (200 / 200 / 401 / 200)](screenshots/test.png) — kết quả chạy thực tế đủ 4 lệnh test, API key đã được ẩn hoàn toàn bằng `Read-Host -AsSecureString`
