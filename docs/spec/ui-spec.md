# Spec — Review UI (hợp đồng hành vi + nghiệm thu)

> **Vai trò:** đây là hợp đồng **hành vi** của màn hình review. Phần **hình thức** nằm ở
> `docs/design/` (tokens/components/layout); **công nghệ** ở `docs/adr/0008-*.md`;
> **API** ở `docs/spec/api-contract.md`; **luật dữ liệu** ở `docs/spec/taxonomy.md`.
>
> Cập nhật cùng PR với `frontend/**` — không để lệch quá 1 PR (AGENTS.md §7).

## 1. Phạm vi

Một màn hình duy nhất (`/`) phục vụ: load state → review item → ghi nhận quyết định của host
(đồng ý / sửa / loại) → export khi gate mở. Cộng 1 luồng upload transcript mới.

**Không thuộc phạm vi:** auth, multi-user, realtime, dark mode, drag-drop, sửa `runs/` trực tiếp,
gọi Jira API, hiển thị lịch sử `review_log` (chỉ ghi, không đọc ở UI này).

## 2. Người dùng & job-to-be-done

Một vai: **host** (người chủ trì cuộc họp). Ngân sách: **2 phút**. Ba việc, theo đúng thứ tự rủi ro:

1. Quét hết **thẻ đỏ** (`confidence < 0.50`) và xử lý từng cái — vì chỉ đỏ mới khoá export (R6).
2. Với mỗi thẻ, **xác minh căn cứ** (evidence + transcript) trước khi đồng ý.
3. Export khi hết đỏ.

Mọi quyết định thiết kế phải phục vụ 3 việc trên. Thứ gì không phục vụ → không làm.

## 3. Hợp đồng dữ liệu ↔ UI

Nguồn chân lý: `pipeline/schema.py` + `GET /api/v1/review`. **UI không được bịa thêm field,
không được suy diễn dữ liệu chưa có**, và không được ẩn một field mà schema coi là bắt buộc.

### 3.1 Envelope (top-level)

| Field | UI |
|---|---|
| `meeting.id/title/date/pipeline_version` | header + brand sidebar |
| `meeting.participants[]` | danh sách chip `Tên · role` dưới tiêu đề |
| `brief.problem` / `brief.outcomes[]` | Alert info dưới header (`layout.md §3`) |
| `no_decision` | Alert warn khi `true` (R3) |
| `stats.by_badge` | số trên 4 ô filter segmented |
| `stats.items_total` | mẫu số của tiến độ `n/total` |
| `known_limitations[]` | `Collapsible` trong sidebar, mặc định đóng, có đếm số |

### 3.2 Item — 6 loại

| Loại | Field bắt buộc hiển thị | Field khác |
|---|---|---|
| `decision` | `content`, `status`, `decided_by`, `confidence`(+reason) | `reason`, `supersedes[]`, `objections[]` (R7), `unresolved_reversal` (R4) |
| `task` | `what`, `owner`, `due`, `confidence`(+reason) | `owner_source`, `due_source`, `due_hint`, `link_to_decision` |
| `blocker` | `content`, `confidence`(+reason) | `needs_action_from`, `severity` |
| `open_issue` | `content`, `next_step`, `confidence`(+reason) | `next_step_owner`, `system_generated` |
| `requirement` | `content`, `confidence`(+reason) | `origin`, `raised_by` |
| `knowledge` | `content`, `confidence`(+reason) | `context`, `tags[]`; **không bắt buộc evidence** |

### 3.3 Evidence

`evidence[]` gồm `quote` · `timestamp` · `speaker` · `turn` · `role_in_discussion`.
UI phải: hiện ≥1 dòng **không cần click**; `timestamp` mở drawer ±4 lượt quanh `turn` (R5);
`role_in_discussion` hiển thị (đây là dữ liệu phân biệt "propose" vs "decide" — không được bỏ).

### 3.4 Ghi (PUT /review)

Mọi mutation gửi `{items, changes:[{item_id, action, old, new}]}`; `action ∈ agree|edit|remove`.
UI **bắt buộc** gửi kèm `changes` (audit — ADR-0004). Sau PUT phải gọi lại `GET` để lấy state mới
(`confirmed_state.json` + `review_log.json` được backend ghi).

## 4. Nghĩa vụ UI theo luật cứng R1–R8

| Luật | Nghĩa vụ UI (kiểm được) |
|---|---|
| R1 | `owner`/`due` = `TBD` phải **nhìn thấy là TBD** (pill vàng), không được hiển thị như đã có giá trị, không được tự điền |
| R2 | `due_source="inferred"` → có dấu hiệu `· suy luận`; `due_hint` hiện trong tooltip. UI **không** diễn giải lại ngày, không tự tính |
| R3 | `no_decision=true` → Alert warn; item `system_generated` có nhãn riêng |
| R4 | `unresolved_reversal=true` → Alert; `supersedes[]` hiển thị dạng lịch sử thu gọn; **objection của bản bị thay thế vẫn xem được** |
| R5 | Bấm `timestamp` → drawer mở đúng `turn` và `<mark>` đúng `quote`. Nếu timestamp bị engine sửa, UI hiển thị timestamp **từ state** (không tự sửa lại) |
| R6 | `export-btn` **`disabled` khi còn bất kỳ item có `confidence < 0.50` chưa được xử lý**; khi disabled phải hiện lý do + số lượng; khi export bị API trả 403 phải liệt kê `red_items` |
| R7 | `decision.objections[]` **phải hiển thị** (nguyên văn). ⚠ Code hiện tại không render field này — đây là lỗi phải sửa trong PR UI |
| R8 | `link_to_decision` trỏ ID không tồn tại → phải hiện dấu cảnh báo, không hiện như link hợp lệ |

## 5. Bàn phím (mục tiêu "review 2 phút")

Bật khi focus **không** nằm trong `input`/`textarea`/`[contenteditable]`.

| Phím | Hành động |
|---|---|
| `j` / `k` | di chuyển focus xuống/lên giữa các card (theo thứ tự đang hiển thị) |
| `a` | Đồng ý card đang focus |
| `e` | mở form Sửa inline, focus vào ô nội dung |
| `x` | Loại card đang focus (có toast hoàn tác — `components.md §8`) |
| `Enter` | mở drawer transcript ở evidence đầu tiên của card đang focus |
| `Esc` | đóng drawer / đóng form sửa |
| `1..4` | lọc nhanh: tất cả / đỏ / vàng / xanh |

Card đang focus phải có chỉ báo thị giác rõ (`ring-2 ring-ring`) và `scrollIntoView({block:'center'})`.

## 6. Trạng thái

Bảng đầy đủ ở `docs/design/components.md §7`. Quy tắc không được vi phạm:
**empty / loading / error / busy luôn ở cấp bề mặt gây ra nó**, không có 1 chỗ "lỗi chung cuối trang".

## 7. A11y tối thiểu (không thương lượng)

- `focus-visible` cho mọi control (token §3).
- Vùng bấm ≥24×24 (timestamp evidence hiện tại ~11px → **phải sửa**), nút chính ≥32×32.
- Nhãn confidence có `aria-label` dạng `"confidence 0.65, mức đỏ"` — không phụ thuộc màu.
- `aria-live="polite"` cho tiến độ `n/total` và toast.
- Sheet: trap focus, `Esc`, trả focus về phần tử đã mở.
- Mọi `input` có `Label` gắn `htmlFor` (hiện tại dùng `<label>` bọc — sai khi có nhiều control).

## 8. Luồng

1. **Load:** nhập meeting id → `GET /review`. Không có state → empty state phân biệt
   `404 not found` vs `chưa chạy cli run`.
2. **Review:** host xử lý thẻ đỏ trước. `Đồng ý` = xác nhận item đúng như engine đề xuất.
   `Sửa` = chỉnh `content` / `owner` / `due` / `link_to_decision` (chỉ những field này).
   `Loại` = item sai hoàn toàn (có hoàn tác).
3. **Confirm:** mỗi hành động PUT ngay (không có nút "Lưu tất cả") → `review_log.json` append.
4. **Export:** chỉ mở khi hết đỏ. `POST /export` → hiện danh sách file đã ghi
   (`runs/<meeting>/<ts>/minutes.md`, `tasks_jira.csv`).
5. **Upload:** chọn file → điền date (bắt buộc, R2) + participants → `POST /meetings/upload`
   → nhận `state` → chuyển thẳng sang review. Lỗi 503 phải nói rõ "LLM chưa sẵn sàng",
   không hiện lỗi chung.

## 9. Acceptance — Definition of Done

Chạy được, không cần đọc code:

**Tự động**

- [ ] `cd frontend && npm run build` xanh
- [ ] `npm run lint` (oxlint) sạch
- [ ] `grep -rE "#[0-9a-fA-F]{3,6}" frontend/src` → chỉ khớp trong `frontend/src/theme.css`
      (file này do PR UI tạo ra — xem `docs/design/tokens.md §0`)
- [ ] `pytest tests -q` vẫn xanh (UI không được làm vỡ `test_api.py`)
- [ ] `data-testid="meeting-input"` và `data-testid="export-btn"` còn nguyên
      (hiện chưa có test UI nào dùng — giữ để test sau này bám vào, `components.md §9`)

**Thủ công — dùng dữ liệu thật**

```powershell
python -m pipeline.cli run --meeting tc5 --llm-fixture data/fixtures/tc5_llm.json
python -m pipeline.cli run --meeting tc2 --llm-fixture data/fixtures/tc2_llm.json
# rồi tự bật: uvicorn backend.api:app --reload  +  npm run dev
```

- [ ] **R6 (tc5, 4 đỏ):** `export-btn` disabled, hiện `Khoá (4 đỏ)`; xử lý lần lượt 4 thẻ đỏ →
      nút mở; xử lý xong hết → `POST /export` trả 200
- [ ] **R7 (tc2 D0 có 2 objection / tc5 D0):** objection đọc được trên UI, nguyên văn
- [ ] **R4 (tc5):** D1/D2 có cảnh báo đảo quyết định; D0 nằm trong lịch sử thu gọn
- [ ] **R2 (tc5 T2):** pill due có `· suy luận`; T0 due `TBD` hiện pill vàng
- [ ] **Empty state (tc5):** cột "Yêu cầu & Phản hồi" rỗng → có `Không có mục nào`
- [ ] **no_decision:** ca có `no_decision=true` → banner hiện (kiểm `runs/<id>/*/state.json` trước)
- [ ] **Keyboard:** `j/k` di chuyển, `a` đồng ý, `x` loại + hoàn tác khôi phục đúng item,
      `Esc` đóng drawer và focus trả về nút timestamp
- [ ] **Evidence:** ≥1 dòng evidence hiện **không cần click**; bấm timestamp → drawer đúng turn
      và câu quote được highlight
- [ ] **Tiến độ:** số `n/total` khớp số item đã xác nhận, cập nhật sau mỗi hành động

## 10. Không thuộc phạm vi PR này

Đổi schema/API, dark mode, drag-drop, responsive mobile <640px (chỉ cần 1 cột cuộn dọc),
TypeScript, i18n, đọc `review_log.json` trên UI.

## 11. Khoảng trống đã biết (trung thực)

1. **R5 chưa có cờ theo item.** `known_limitations` là mảng chuỗi, không có `flags` trên `Item`
   → UI không tô được "item này bị evidence_mismatch". Cách xử lý tạm ở `components.md §4`
   (hiển thị đầy đủ `known_limitations`). Sửa sạch cần thêm `Item.flags` = **đổi schema**
   → prompt + golden + UI cùng lúc → cần ADR riêng, chưa làm ở PR này.
2. **`Loại` không xoá dữ liệu thật** — item vẫn nằm trong `runs/` (đúng theo ADR-0004: audit append).
   UI chỉ ẩn khỏi phiên review hiện tại. Điều này **không** được mô tả là "xoá vĩnh viễn" trên UI.
3. **Chưa có test UI tự động** (chưa có Playwright/RTL). Checklist §9 hiện là thủ công +
   `data-testid` đã đặt sẵn để viết test sau.
4. **`brief` có thể null** (fixture mode bỏ brief) → UI phải chịu được việc không có brief.
