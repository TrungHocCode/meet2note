# Components — meet2note UI (v2 · shadcn/ui + Tailwind)

> Hiện thực: `frontend/src/App.jsx` + `frontend/src/components/ui/*` (shadcn, copy-paste).
> Token: `docs/design/tokens.md` · Bố cục: `docs/design/layout.md` ·
> Hợp đồng hành vi + acceptance: `docs/spec/ui-spec.md` · Công nghệ: `docs/adr/0008-*.md`.
>
> **Quy tắc chung:** mọi control có đủ `default / hover / active / focus-visible / disabled`;
> **disabled luôn kèm lý do hiển thị** (không bao giờ chỉ xám đi).

## 0. Map sang component shadcn

| Thành phần | shadcn | Ghi chú |
|---|---|---|
| Nút | `button` | chỉ dùng 3 tone ở §1 |
| Thẻ item, khối sidebar | `card` | thẻ item tự compose thêm phần evidence/meta |
| Nhãn confidence, pill meta | `badge` | biến thể tự thêm `conf-red/amber/green` |
| Drawer transcript | `sheet` | `side="right"`, có backdrop (Radix Dialog) |
| Lý do confidence | `tooltip` | nội dung = `confidence_reason` |
| Tiến độ review | `progress` | + số `n/total` bên cạnh (không chỉ thanh) |
| Gate / limitations | `alert` | biến thể `warn`/`ok` |
| Nhóm sidebar, lịch sử supersedes | `collapsible` | thay `<details>` |
| Filter confidence | `toggle-group` | dạng segmented |
| Vùng cuộn | `scroll-area` | cột + body drawer |
| Toast + hoàn tác | `sonner` | 1 chỗ duy nhất: `Toaster` ở `App.jsx` |
| Đang tải | `skeleton` | cho `busy` >300ms |

## 1. Button

| Tone | Dùng cho | Default | Hover | Active | Disabled |
|---|---|---|---|---|---|
| `default` (primary) | Load, Export (khi gate mở), Upload + chạy | `bg-primary text-primary-foreground` `rounded-xl` `px-4 py-2` `font-semibold` | `brightness-95` | `brightness-90` | `bg-muted text-muted-foreground` + `cursor-not-allowed` + **chữ nói lý do** (vd `Khoá (2 đỏ)`) |
| `outline` (ghost) | Đóng sheet, Sửa, Huỷ | `bg-card border` | `bg-muted` | `bg-muted` đậm hơn | như trên |
| `destructive` | Loại | `text-destructive border-destructive/30 bg-card` | `bg-conf-red-bg` | viền `destructive` | như trên |

- Vùng bấm tối thiểu **32×32** (kể cả icon-only). Nút chính cao **36–40px**.

## 2. Card item (đơn vị review)

Thứ tự trên card (từ trên xuống):

1. **Head:** `id` (mono 12px, muted) · nhãn loại (Quyết định/Công việc/…) · nhãn confidence (§3)
   · pill `cần xử lý` nếu là thẻ đỏ chưa xử lý.
2. **Nội dung:** `item.content` (hoặc `item.what` với task) — `text-sm`, `font-medium`, `leading-relaxed`.
3. **Cảnh báo semantic** nếu có (§4).
4. **Meta pills — 1 pattern duy nhất `nhãn: giá trị`:** task `Người làm / Hạn / Theo QĐ`;
   decision `Người chốt / Thay thế` (trống → `quyết định gốc`); blocker `Người gỡ / Mức nặng`
   (Thấp-Trung bình-Cao + tooltip giải thích); open_issue `Người tiếp` (+ pill `hệ thống tạo`);
   requirement `Nguồn` (Khách hàng/Nội bộ/Đối tác/Chưa rõ + tooltip) / `Người nêu`;
   knowledge tags + `Ngữ cảnh`. Thiếu → `—` mờ (không im lặng bỏ qua, trừ link/hint).
   TBD → pill vàng (R1). Câu dài (lý do/next_step) KHÔNG để trong pill (pill `nowrap`
   gây tràn) — render dòng text wrap riêng.
5. **Evidence — HIỆN SẴN, không giấu sau click** (sửa so với v1):
   - Hiện tối đa **2** dòng evidence; nhiều hơn → nút `+N evidence` mở phần còn lại.
   - Mỗi dòng: `[timestamp]` (link-button, target ≥24×24, hover gạch chân + màu `primary`) ·
     speaker (600) · `role_in_discussion` (muted 10–11px) · quote trong `<q>` (italic, 12px/1.6).
   - Dòng evidence: nền `--color-evidence-bg`, vạch trái 2px `--color-evidence-rule`, radius phải.
   - Lý do: evidence là căn cứ tồn tại của sản phẩm — giấu nó sau 1 cú click là sai thiết kế.
   - Knowledge không có evidence → không render khối này (schema cho phép).
6. **Hành động:** `Đồng ý / Sửa / Loại` equal-width, `ok`/`outline`/`destructive`.
   - Hiện khi `hover` **hoặc** card đang `focus` (bàn phím) **hoặc** thẻ đỏ (đỏ luôn cần hành động).

- Card nghỉ: `border` 1px + **vạch trái 4px + nền tint nhạt theo mức confidence**
  (đỏ `conf-red`, vàng `conf-amber`, xanh `conf-green`) — toàn ô mang màu mức độ,
  không chỉ badge (phản hồi review UI: chỉ badge có màu gây khó quét).
  Hover: `shadow-card` + `-translate-y-px`, `duration-150`.
- Mọi text trong card (`content`, quote, pill) phải `break-words` — lý do dài không
  được tràn khung (lỗi thực tế: reason dài tràn khỏi card quyết định).
- Thẻ đỏ: `border-conf-red/40` + vạch trái 3px `conf-red` + nền `conf-red-bg/40`.
- Thẻ đã xử lý: `opacity-60` + pill `✓ đã xác nhận`.
- Cột sắp xếp theo **rủi ro tăng dần** (đỏ → vàng → xanh); thẻ đã xử lý trôi xuống cuối.
- **Discarded** (decision `status=discarded`): nằm trong `Collapsible` ngay dưới decision `final`
  thay thế nó; chữ 11–12px muted, nền nhạt — không cạnh tranh thị giác với `final` (R4).
  Objection của bản discarded phải hiển thị được (§4, R7).

## 3. Badge confidence

| Mức | Token | Cỡ |
|---|---|---|
| `< 0.50` đỏ | chữ `--color-conf-red`, nền `--color-conf-red-bg` | `text-xs font-semibold rounded-full px-2` |
| `0.50–0.75` vàng | chữ `--color-conf-amber`, nền `--color-conf-amber-bg` | như trên |
| `≥ 0.75` xanh | chữ `--color-conf-green`, nền `--color-conf-green-bg` | như trên |

- **Luôn kèm số** (`0.65`) — màu không phải kênh thông tin duy nhất.
- Số confidence bọc `Tooltip`, nội dung = **`item.confidence_reason`** (schema đã có:
  `"conf_llm=0.95; evidence_mismatch -0.30"`). Host phải biết *vì sao* 0.65, không chỉ *bao nhiêu*.
  Phần này v1 bỏ sót, code hiện tại cũng không hiển thị.

## 4. Cảnh báo semantic & marker (map R1–R8 → UI)

Đây là phần v1 **bỏ trống hoàn toàn** trong khi schema đã mang đủ dữ liệu.

| Field / luật | Hiển thị | Luật |
|---|---|---|
| `decision.objections[]` | Alert warn trên card: `⛔ Objection (N)` + `Collapsible` liệt kê từng câu (nguyên văn) | **R7** — không xoá tranh luận. ⚠ **Code hiện tại không render field này ở đâu cả** |
| `decision.unresolved_reversal` | Alert destructive: `⚠ Đảo quyết định (A→B→A) — cần host chốt` | R4 |
| `task.owner/due = "TBD"` | Pill vàng `TBD` (không in chữ xám như hiện tại) | R1 |
| `owner_source="explicit"` / `due_source="inferred"` | Hậu tố nhỏ `· suy luận` trên pill (`inferred`), không thêm gì với `explicit` | R1/R2 |
| `task.due_hint` | Trong `Tooltip` của pill due: `hint: "thứ 2 tuần sau"` | R2 |
| `open_issue.system_generated` | Pill `hệ thống tạo` + nền `--color-warn-bg` | R3 (O_SYS) |
| `meeting.no_decision = true` | Alert warn ngay dưới header: `Họp không chốt nội dung nào — xem Open Issue` | R3 |
| `known_limitations[]` | `Collapsible` trong sidebar, có **đếm số**, mặc định đóng; mở ra thì nhóm theo loại (merge/evidence/due/R4) | Trung thực |
| `link_to_decision` | Pill `🔗 D1`; nếu trỏ ID không tồn tại → pill destructive `🔗 D9 (không tồn tại)` | R8 |

### Chưa chốt: hiển thị `evidence_mismatch` (R5) thế nào

`known_limitations` là **mảng chuỗi** (`"item D1 (decision): evidence_mismatch (R5)"`), không có
cờ theo từng item. Hai lựa chọn:

- **(a) Tạm thời, không đổi schema:** UI parse chuỗi `known_limitations` để tô nhãn item liên quan.
  Rẻ nhưng dựa vào định dạng chuỗi → dễ vỡ khi đổi câu chữ (nguy hiểm).
- **(b) Sạch:** thêm field tùy chọn `flags: list[str]` vào `Item` trong `pipeline/schema.py`.
  Theo AGENTS.md §5, đổi schema = **phải sửa prompt + UI + golden cùng lúc** → cần ADR mới.

**Đề xuất:** làm (b) nhưng ở PR riêng; ở PR UI này tạm **không** tô gì cho R5 ngoài việc
`known_limitations` đã được hiển thị đầy đủ (đủ để host tự thấy). Ghi vào `ui-spec.md §11` như gap.

## 5. Input / Textarea / Label / Filter

- `Input`/`Textarea`: `border-input rounded-md px-3 py-2 text-sm`, focus
  `outline-ring outline-2 outline-offset-0` + viền primary.
- `Label` luôn gắn `htmlFor` (không dùng `<label>` bọc ngoài như hiện tại).
- **Filter confidence = `ToggleGroup` segmented** (4 ô: tất cả / 🔴 n / 🟡 n / 🟢 n) thay cho
  4 radio dọc — tiết kiệm chỗ sidebar, số lượng nằm ngay trên nhãn.

## 6. Sheet — Drawer transcript

- `Sheet side="right"`, rộng `min(520px, 92vw)`, full-height, `shadow-drawer`, **có backdrop mờ**
  (`bg-foreground/40`). Backdrop không chỉ để đẹp: nó nói rõ "đây là lớp tạm, không phải màn hình mới".
- Head sticky: tên meeting + `nguồn: tc5_fail.txt` + nút Đóng ✕.
- Body: `ScrollArea`, cửa sổ **±4 lượt** quanh `evidence.turn` (khớp `api-contract.md`),
  tự cuộn tới lượt đích.
- Turn đích: nền `--color-hl-bg` + viền `--color-hl-border`, và **`<mark>` đúng câu `quote``**
  của evidence (R5 — host phải thấy đúng câu đã được trích).
- Đóng: `✕` / `Esc` / click backdrop / click lại cùng timestamp.
  **`Esc` là bắt buộc, không phải nice-to-have** (v1 ghi "nice-to-have" — trái với `layout.md`).
- Focus: mở sheet → trap focus trong sheet; đóng → trả focus về nút timestamp đã bấm.

## 7. Trạng thái màn hình (State matrix)

v1 đặt tiêu đề "(mọi trạng thái)" nhưng chỉ có 4 trạng thái của button. Bảng đầy đủ:

| Bề mặt | empty | loading | error | partial | dài (long list) |
|---|---|---|---|---|---|
| Sidebar | — | `Skeleton` 3 dòng | `Alert destructive` **ngay dưới khối gây lỗi** (không dồn cuối) | — | `ScrollArea` |
| Chọn meeting | chưa load → `Chưa load meeting` + gợi ý `tc1..tc5` | nút `Load` → `Đang tải…` + disabled | 404 → `Chưa chạy cli run cho meeting này` (phân biệt rõ 404 vs 503) | — | — |
| Header | — | — | — | `no_decision=true` → Alert warn | — |
| Cột | **Empty state**: viền đứt + `Không có mục nào` (kèm gợi ý lọc nếu đang bật filter) | `Skeleton` 2 thẻ | — | — | cuộn riêng từng cột |
| Card | — | — | — | confidence_reason rỗng → Tooltip ẩn | evidence >2 → `+N` |
| Export | gate mở → Alert ok `Đủ điều kiện export` | `Đang export…` + disabled | 403 → liệt kê `red_items`; 400 `not_confirmed`; 503 → hướng dẫn bật LLM | — | — |
| Upload | chưa chọn file → chặn + nói rõ | `Đang chạy pipeline…` (có thể lâu) | 400/422/503 phân biệt thông điệp | — | — |
| Drawer | transcript 404 → Alert trong sheet | `Skeleton` 5 dòng | 404 → nói rõ không tìm thấy transcript | turn đích ngoài phạm vi → cuộn tới gần nhất | `ScrollArea` |

Quy tắc: **error và busy luôn ở cấp bề mặt gây ra nó**, không có 1 chỗ "error chung cuối trang".

## 8. Toast & xác nhận

- **`Loại` phải có hoàn tác:** bấm → xoá khỏi danh sách ngay + `sonner` toast
  `Đã loại T2 · [Hoàn tác]` (giữ 8s). Hoàn tác phục hồi item về đúng vị trí.
  Lý do: hiện tại `Loại` xoá luôn, không xác nhận, không hoàn tác — `review_log.json` có ghi
  nhưng host không thấy.
- Không dùng `window.confirm` (chặn UI, không test được).
- `Đồng ý` / `Sửa`/lưu không cần toast (thay đổi đã thấy ngay trên card: pill `✓ đã xác nhận`).

## 9. Hợp đồng testid + a11y

**`data-testid` phải giữ nguyên** — không phải vì test hiện tại dùng (không có test UI nào),
mà vì `docs/spec/ui-spec.md §9` đã cam kết dùng chúng làm điểm bám cho test UI sẽ viết.
Gate R6 được bảo vệ ở tầng API (`tests/test_api.py`), **không** phụ thuộc testid.

| testid | Phần tử | Bắt buộc |
|---|---|---|
| `meeting-input` | ô nhập meeting id | giữ |
| `export-btn` | nút Export | giữ; **`disabled` khi còn thẻ đỏ** |
| `upload-file`, `upload-submit` | form upload | thêm mới |
| `card-{id}`, `card-{id}-evidence`, `card-{id}-agree` | thẻ + evidence + nút | thêm mới (phục vụ test UI) |

A11y tối thiểu:

- `focus-visible` outline 2px cho **mọi** control (§3 tokens).
- Badge/trạng thái có tên đọc được (`aria-label="confidence 0.65, mức đỏ"`), không chỉ emoji.
- `aria-live="polite"` cho: số `n/total` đã xác nhận và toast.
- Sheet: trap focus + `Esc` + trả focus.
- Bàn phím: xem `docs/spec/ui-spec.md §5` (không lặp ở đây).
