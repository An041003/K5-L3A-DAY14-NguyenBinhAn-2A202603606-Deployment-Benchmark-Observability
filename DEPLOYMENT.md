# Deployment Information — Day 14

**Status: PENDING — chưa triển khai public cloud.**

## Public URL
PENDING: thay bằng domain thực từ Railway sau khi deploy, không dùng localhost khi nộp.

## Platform: Railway (lựa chọn triển khai)
1. Push repo bài làm lên GitHub của bạn, không push vào repo giảng viên.
2. Railway: New Project → Deploy from GitHub → chọn repo, thêm Redis service.
3. Agent Settings: Root Directory `/06-lab-complete`; Config File Path `/06-lab-complete/railway.toml` nếu Railway chưa nhận config. Dockerfile nằm trong root đã chọn.
4. Variables: REDIS_URL tham chiếu Redis private URL do Railway cung cấp (chọn biến reference trong UI), AGENT_API_KEY sinh random, ENVIRONMENT=production, RATE_LIMIT_PER_MINUTE=10, DAILY_BUDGET_USD=10, MONTHLY_BUDGET_USD=10, LOG_LEVEL=INFO. PORT do platform cấp; nếu phải tự đặt thì 8000. Không công khai Redis.
5. Deploy; Networking → Generate Domain. Chụp dashboard, running, test; che secrets.

## CP6 — bốn mã HTTP (WSL2/Linux)
```bash
BASE='https://YOUR-REAL-DOMAIN'
read -rsp 'API key: ' AGENT_API_KEY; echo
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'
unset AGENT_API_KEY
```

| Check | Expected | Actual |
|---|---|---|
| GET /health | 200 | PENDING |
| GET /ready | 200 | PENDING |
| POST /ask không key | 401 | PENDING |
| POST /ask có key | 200 | PENDING |

Chụp `screenshots/test.png` với 4 status thực, không hiển thị key. Sau đó chạy grader đầy đủ trong WSL2 tại `06-lab-complete` với `--public-url "$BASE"` nếu muốn kiểm tra thêm URL. Nếu `/ready`=503, kiểm tra Redis URL private, kết nối và trạng thái Redis. Không dùng GET /ask (405).

## Screenshots
- screenshots/dashboard.png — PENDING
- screenshots/running.png — PENDING
- screenshots/test.png — PENDING

Không commit API key, Redis URL có mật khẩu hoặc ảnh chứa credentials. Nếu dùng Render, chọn Blueprint config `06-lab-complete/render.yaml` và cung cấp Redis URL; kiểm tra root directory / Dockerfile path trong UI.
