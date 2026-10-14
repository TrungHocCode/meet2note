# Runbook — link chạy thử (FE Vercel + BE tunnel từ máy bạn)

> Mục đích: cho người khác dùng thử mà không deploy backend — máy bạn làm server,
> Cloudflare Tunnel mở cửa, frontend lên Vercel gọi về.

## Kiến trúc demo

```
Người thử → https://meet2note.vercel.app (Vercel, tĩnh)
              │ fetch + Bearer + cookie (cross-site)
              ▼
         https://<ten>.cfargotunnel.com (cloudflared, máy bạn)
              ▼
         FastAPI :8000 → Postgres :5434 (KHÔNG expose) + Ollama :11434 (KHÔNG expose)
```

## 1. Chuẩn bị (1 lần)

```powershell
winget install --id Cloudflare.cloudflared   # hoặc tải từ developers.cloudflare.com
cloudflared tunnel login                     # mở browser, chọn domain (free)
# Đặt tên tunnel cố định để URL không đổi mỗi lần chạy:
cloudflared tunnel create m2n-demo
```

Ghi lại URL: `https://m2n-demo.<hash>.cfargotunnel.com` (xem bằng
`cloudflared tunnel info m2n-demo`).

## 2. Bật backend chế độ demo

`.env` thêm (ngoài các biến sẵn có):

```
CORS_ORIGINS=https://meet2note.vercel.app
COOKIE_CROSS_SITE=1
```

Khởi động lại API + mở tunnel (2 terminal giữ nguyên khi demo):

```powershell
# Terminal 1:
.\.venv\Scripts\python.exe -m uvicorn backend.api:app --port 8000
# Terminal 2:
cloudflared tunnel run --url http://localhost:8000 m2n-demo
```

> `COOKIE_CROSS_SITE=1` bắt buộc vì refresh cookie đi qua site khác
> (Vercel ≠ tunnel) — browser chỉ gửi khi `SameSite=None; Secure`.
> Dùng link HTTPS của tunnel nên `Secure` hợp lệ.

## 3. Đẩy frontend lên Vercel

```powershell
cd frontend
npm i -g vercel   # lần đầu
vercel --prod --build-env VITE_API_URL=https://m2n-demo.<hash>.cfargotunnel.com
```

Hoặc trên dashboard Vercel: Settings → Environment Variables →
`VITE_API_URL=https://m2n-demo.<hash>.cfargotunnel.com` → Redeploy.

## 4. Checklist trước khi gửi link

- [ ] Máy bật + Ollama đang chạy (`ollama list` thấy model).
- [ ] Mở URL Vercel ở trình duyệt ẩn danh: đăng ký được, login được.
- [ ] Upload 1 file test → pipeline chạy xong → export → tải được file.
- [ ] Tắt máy = demo tắt — hẹn trước với người thử.

## Lưu ý bảo mật

- Chỉ expose port API `:8000`. **Không** mở tunnel cho Postgres `:5434` hay Ollama.
- Người lạ tự đăng ký được (MVP mở register) nhưng chỉ thấy meeting của họ
  (owner isolation đã test ở `tests/test_auth.py`).
- Hết demo: `cloudflared tunnel delete m2n-demo`, gỡ `COOKIE_CROSS_SITE` nếu không dùng nữa.
