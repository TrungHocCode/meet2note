# ADR-0008 — Tailwind CSS v4 + shadcn/ui cho frontend review (kèm lớp design tokens)

- Status: Accepted
- Date: 2026-10-14

## Context

UI review hiện tại là CSS thuần: `frontend/src/App.jsx` (748 dòng) + `App.css` (415 dòng)
với **~60 giá trị hex thô**, không token, không component library. Hệ quả cụ thể:

- Không có chỗ định nghĩa "màu đỏ nghĩa là confidence < 0.50" → mỗi chỗ tự chọn hex.
- UI là **mặt tiếp xúc duy nhất** với 8 luật cứng R1–R8 (gate R6, R5 evidence, R1/R2 TBD…),
  nhưng không có lớp component nào để biểu diễn trạng thái (loading/empty/error/disabled-có-lý-do).
- Các thành phần a11y (focus trap cho drawer, `aria-live`, tooltip, toast có hoàn tác)
  nếu tự viết sẽ tốn >400 dòng CSS/JS và rất dễ sai.

`docs/design/*` đã mô tả phần hình thức (tokens/components/layout) nhưng **không nói dùng
công nghệ nào** — trong khi repo đang bàn cả 2 hướng (CSS thuần + biến, hoặc Tailwind + shadcn).

Ràng buộc repo: đây là prototype MVP, KHÔNG production. Gate R6 được bảo vệ ở **tầng API**
(`tests/test_api.py::test_export_403_when_red_items_exist`), **không** bằng `data-testid`.
`data-testid` (`meeting-input`, `export-btn`) hiện **chưa có test nào dùng** — giữ nguyên vì
`docs/spec/ui-spec.md §9` đã cam kết dùng chúng cho test UI sẽ viết sau; đổi tên chỉ để đẹp là
thay đổi vô ích kèm rủi ro.

## Decision

1. **Tailwind CSS v4** qua plugin `@tailwindcss/vite` (không dùng PostCSS config riêng).
2. **shadcn/ui** theo mô hình copy-paste (code thuộc repo, không phải dependency runtime).
   `components.json` đặt `"tsx": false` vì frontend là JS, không phải TS.
3. **Token 2 tầng:**
   - Tầng nền: đặt tên **tương thích shadcn** (`--background`, `--foreground`, `--card`,
     `--primary`, `--destructive`, `--muted`, `--border`, `--ring`, `--radius`) để component
     shadcn hoạt động không cần override.
   - Tầng domain (riêng meet2note): confidence 3 mức, `--warn/--ok/--info`, highlight transcript,
     màu evidence — **nằm ngoài namespace shadcn**.
   - Khai trong `App.css` bằng `@theme` (+ `:root` cho biến không sinh utility).
     **Không có hex thô ngoài `@theme`/`:root`.**
4. **Bộ component lấy từ shadcn (chỉ những cái dùng thật):**
   `sidebar`, `card`, `badge`, `button`, `sheet` (drawer transcript), `tooltip`
   (lý do confidence), `progress` (tiến độ review), `alert` (gate/limitations), `collapsible`,
   `toggle-group` (filter segmented), `scroll-area`, `separator`, `input`, `textarea`, `label`,
   `skeleton` (busy), `sonner` (toast + hoàn tác).
5. **KHÔNG lấy** `data-table`, `chart`, `drawer` (Vaul), `form` (react-hook-form):
   không có nhu cầu ở phạm vi này.
6. **Font:** Be Vietnam Pro (heading) + Inter (body), self-host qua `@fontsource`, **bắt buộc
   subset `vietnamese`**. Lý do: tiếng Việt dấu stacked (hỏi/ngã) cần kiểm soát font, không
   phó mặc cho font hệ điều hành — chi tiết test dấu ở `docs/design/tokens.md §4`.

**Đính chính do ADR này:** token thương hiệu phải tên là `--primary` (không phải `--accent`).
Trong hệ shadcn, `--accent` đã mang nghĩa khác (nền hover nhạt). Đặt sai tên sẽ làm mọi
component shadcn sai màu. `docs/design/tokens.md v2` đã sửa theo.

## Consequences

- (+) Trạng thái (hover/focus/disabled/loading/empty) có sẵn chuẩn → tập trung vào 8 luật cứng
  thay vì tự viết lại button/badge/sheet.
- (+) ràng buộc "UI chỉ đọc `state.json`" dễ giữ hơn: component không tự bịa thêm field.
- (+) `App.css` từ ~415 dòng CSS tay + 60 hex → còn `@theme` token + vài `className`.
- (−) Thêm ~10 dev dependency (`tailwindcss`, `@tailwindcss/vite`, `class-variance-authority`,
  `clsx`, `tailwind-merge`, `lucide-react`, `radix-ui`, `sonner`, `@fontsource/*`, `tw-animate-css`).
  Chấp nhận: đây là prototype 1 trang nhưng UI là mặt tiếp xúc duy nhất với 8 luật cứng.
- (−) Code shadcn về sau không tự cập nhật (đúng bản chất copy-paste). Chấp nhận: dừng ở số
  component đã liệt kê, không "lấy thêm cho vui".
- (−) Rủi ro CLI sinh `.tsx` → phải set `tsx: false` và **kiểm lại sau mỗi lần thêm component**.
- (−) Rủi ro vỡ gate R6 khi thay Button/disabled. Bù lại: acceptance checklist bắt buộc
  `export-btn` disabled khi còn thẻ đỏ (xem `docs/spec/ui-spec.md §9`).
- Bắt buộc: giữ nguyên `data-testid` hiện có; migrate `App.css` trong **cùng PR** với `App.jsx`
  (AGENTS.md §7: code lệch docs thì sửa docs trong cùng PR).

## Alternatives considered

- **Giữ CSS thuần + biến** (phương án ban đầu của `tokens.md v1`): loại vì vẫn phải tự viết
  button/badge/sheet/tooltip/toast + a11y (focus trap, aria, `aria-live`) — trùng công với
  thứ Tailwind+shadcn cho sẵn, mà rủi ro a11y sai cao hơn.
- **Mantine**: đủ đồ (notification, spotlight) nhưng là runtime nặng, theme khó ra "calm-light",
  và với 1 trang review thì thừa.
- **Radix/Base UI thuần + CSS tự viết**: giữ được a11y nhưng vẫn phải tự style 100% → chậm hơn
  mà không được lợi gì thêm so với Tailwind.
- **Tailwind + tự viết component (không shadcn)**: mất chuẩn a11y đã được kiểm sẵn; không có lý do.
- **Đổi sang TypeScript khi adopt shadcn**: loại ở PR này — phạm vi là UI, không phải type layer;
  đổi ngôn ngữ sẽ làm PR trộn 2 mục tiêu (AGENTS.md: 1 mục tiêu / 1 thay đổi).
