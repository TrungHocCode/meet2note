# Layout — meet2note UI (v2 · Tailwind + shadcn)

> Token: `docs/design/tokens.md` · Component: `docs/design/components.md` ·
> Hợp đồng hành vi: `docs/spec/ui-spec.md`.

## 1. Sidebar (mặc định 280px, gom 3 nhóm `Collapsible`)

Hiện tại 5 khối chồng nhau (load / filter / export / upload / error) gây clutter. Gom lại:

```
meet2note                                   ← brand + meeting id · date · pipeline_version
├── ① Meeting    : input id + Load + trạng thái (đang tải / 404 / 503)
├── ② Review     : tiến độ n/total + Progress · filter segmented · gate Alert + nút Export
└── ③ Upload     : Collapsible chứa file/id/title/date/participants + nút chạy + message
```

- **Lỗi nằm ngay dưới khối gây ra nó**, không dồn cuối sidebar (khác hiện tại).
- Nút **Export nằm trong nhóm ②** (cạnh gate Alert) — không tách rời khỏi lý do khoá/mở của nó.
- Form Upload **mặc định đóng** (`Collapsible`) — host 90% thời gian chỉ review, không upload.

## 2. Sidebar theo breakpoint + lưới cột (sửa so với v1)

**v1 sai:** `≥1400px: 4 cột; <1400px: 2 cột`. 1366×768 là độ phân giải laptop phổ biến →
host mặc định mất luôn chế độ 4 cột, tệ hơn hiện tại và trái `spec/export-format.md` ("Main 4 cột").
Ở 1366: `1366 − 280 = 1086` → vẫn đủ **271px/cột**, tức là 4 cột vẫn sống được.

| Breakpoint | Sidebar | Lưới cột | Ghi chú |
|---|---|---|---|
| `xl` ≥ 1280px (Tailwind mặc định) | mở, 280px | **4 cột** | trạng thái chuẩn — chứa cả 1366×768 |
| `lg` 1024–1279px | **thu thành rail 56px** (icon + `Sheet` mở rộng khi cần) | 4 cột | thu sidebar **trước**, không hạ cột |
| `md` 768–1023px | rail 56px | 2 cột | |
| < `md` | rail 56px | **1 cột**, cuộn dọc | ≥640px vẫn 1 cột, không cố nhồi 2 |

Nguyên tắc: **thu sidebar trước, hạ số cột sau.** Cột không bao giờ hẹp dưới ~240px.
Không bóp cỡ chữ để nhét cột (đã có tiền lệ xấu: card hiện tại 13px trên 4 cột dày).

- Header meeting (title — date · id · `pipeline_version`): `sticky top-0` nhẹ (nền `card/90` +
  `backdrop-blur`), cao tối đa 64px khi cuộn.
- Mỗi cột: tiêu đề + **số lượng** (`text-xs` muted, bọc `rounded-full` nền muted).
- Mỗi cột cuộn **riêng** (`ScrollArea`) trên màn ≥1280px; dưới `xl` để cả trang cuộn.

## 3. Vị trí Brief (chốt — v1 để mơ hồ ở 2 file)

Brief (`state.brief.problem` + `outcomes`) nằm ở **main, ngay dưới header meeting**, dạng `Alert`
nền `--color-info-bg`. **Không** ở sidebar.

Lý do: brief là ngữ cảnh để *đọc* các thẻ, không phải điều khiển. Đặt trong sidebar cạnh filter
sẽ trộn "ngữ cảnh" với "điều khiển".

`outcomes` render: mỗi dòng + `ref_ids` dạng pill nhỏ (`D1` `T1`) — để host thấy brief trỏ tới
đúng item nào (R8).

## 4. Drawer transcript (`Sheet`)

- Fixed-right `min(520px, 92vw)`, **có backdrop mờ** `bg-foreground/40`.
- **Không đè sidebar** (sidebar vẫn thao tác được? → **không**: backdrop chặn toàn bộ, để buộc
  host kết thúc việc xem transcript trước khi tiếp tục. Đây là chủ ý, không phải thiếu sót).
- **Vấn đề v1 không giải quyết:** drawer 480px che cột 4 → host mất ngữ cảnh "Yêu cầu & Phản hồi".
  Cách xử lý đã chọn: backdrop + **shadow-drawer mạnh** + nút `Đóng (Esc)`; chấp nhận che cột vì
  host thường chỉ mở drawer 3–5 giây để xác minh 1 câu quote. **Không** làm "push layout"
  (làm cột co giật mỗi lần mở — tệ hơn).
- Nội dung: ±4 lượt quanh `evidence.turn`, highlight lượt đích + `<mark>` đúng câu quote (R5).
  Chi tiết: `components.md §6`.

## 5. Không làm trong phase này

- **Dark mode** — để backlog. Token đã đặt tên trung tính (semantic, không phải `--white-bg`)
  nên thêm theme sau này chỉ là thêm 1 khối `:root` khác. Chưa làm vì sẽ gấp đôi công kiểm a11y contrast.
- **Drag-drop Kanban** — 4 cột là `item.type` do LLM gán, **không phải** trạng thái host di chuyển.
  Kéo thả ở đây là vô nghĩa; nếu muốn đổi loại item thì đó là "Sửa", không phải kéo thả.
- **Desktop app / mobile native**, virtualized list — chưa cần ở quy mô MVP (≤ ~30 item/họp).
- **Auto-refresh / realtime** — ngoài phạm vi (README: "KHÔNG làm realtime").
