# Design tokens — meet2note UI (v2 · Tailwind v4 + shadcn)

> **Hợp đồng:** mọi giá trị màu/khoảng cách/bo góc/font trong `frontend/src/**` phải lấy
> từ file này. Không thêm token mới khi chưa sửa file này.
> Công nghệ: `docs/adr/0008-tailwind-shadcn-va-design-tokens.md` ·
> Hình thức tổng thể: `docs/design/layout.md`, `docs/design/components.md`.
> Nguồn tham chiếu: calm-light (trắng + 1 accent), học từ review Otter/tl;dv.

## 0. Khai token ở đâu (Tailwind v4)

Toàn bộ token khai **một chỗ duy nhất**: `frontend/src/theme.css`
(**file này sẽ được tạo ở PR UI — chưa tồn tại ở commit hiện tại**; `App.css` chỉ còn phần
bố cục riêng, component dùng utility của Tailwind).
Bằng `@theme` — `@theme` sinh ra utility (`bg-primary`, `text-muted-foreground`, `shadow-card`).
Biến nào **không** cần sinh utility thì khai trong `:root`.

```css
@import "tailwindcss";

@theme {
  /* tầng nền — tương thích shadcn */
  --color-background: #f8fafc;
  --color-foreground: #1f2937;
  --color-card: #ffffff;
  --color-primary: #3b5bdb;
  --color-primary-foreground: #ffffff;
  --color-muted: #f1f5f9;
  --color-muted-foreground: #6b7280;
  --color-accent: #f1f5f9;            /* ⚠ nền hover nhạt — XEM §5.1 */
  --color-destructive: #dc2626;
  --color-border: #e5e7eb;
  --color-ring: #3b5bdb;

  /* tầng domain — riêng meet2note, ngoài namespace shadcn */
  --color-conf-red: #dc2626;
  --color-conf-red-bg: #fef2f2;
  --color-conf-amber: #92400e;
  --color-conf-amber-bg: #fffbeb;
  --color-conf-green: #047857;
  --color-conf-green-bg: #ecfdf5;
  --color-warn-bg: #fffbeb;
  --color-ok-bg: #ecfdf5;
  --color-info-bg: #f0f9ff;
  --color-hl-bg: #fef9c3;
  --color-hl-border: #facc15;
  --color-evidence-bg: #f8fafc;
  --color-evidence-rule: #cbd5e1;

  --radius: 10px;
  --shadow-card: 0 4px 12px rgb(15 23 42 / 0.08);
  --shadow-drawer: 0 8px 24px rgb(15 23 42 / 0.12);

  --font-sans: "Inter", system-ui, sans-serif;
  --font-heading: "Be Vietnam Pro", "Inter", system-ui, sans-serif;
}

:root {
  --radius-sm: calc(var(--radius) - 4px);   /* 6 */
  --radius-md: calc(var(--radius) - 2px);   /* 8 */
  --radius-lg: var(--radius);               /* 10 */
  --radius-xl: calc(var(--radius) + 4px);   /* 14 */
}
```

**Quy tắc kiểm được:** `grep -rE "#[0-9a-fA-F]{3,6}" frontend/src` → chỉ được khớp trong
`frontend/src/theme.css` (khối `@theme`/`:root`). Khớp ở file khác = lỗi.

## 1. Token tầng nền (tương thích shadcn)

| Token | Giá trị | Dùng cho |
|---|---|---|
| `--color-background` | `#f8fafc` | Nền app |
| `--color-foreground` | `#1f2937` | Chữ chính |
| `--color-card` | `#ffffff` | Card, sidebar, sheet, popover |
| `--color-primary` | `#3b5bdb` (indigo) | **CTA duy nhất:** Load, Export (mở), Upload + chạy |
| `--color-primary-foreground` | `#ffffff` | Chữ trên CTA |
| `--color-muted` / `--color-muted-foreground` | `#f1f5f9` / `#6b7280` | Nền phụ, subtitle, timestamp, role |
| `--color-accent` | `#f1f5f9` | **Nền hover nhạt** của item trong menu/list (nghĩa của shadcn — không phải màu thương hiệu) |
| `--color-destructive` | `#dc2626` | Nút Loại, lỗi, chữ badge đỏ |
| `--color-border` / `--color-input` / `--color-ring` | `#e5e7eb` / `#e5e7eb` / `#3b5bdb` | Viền card/divider · viền input · vòng focus |

Hover/active của `primary`: `hover:brightness-95` / `active:brightness-90`
(không hardcode thêm 2 hex như v1 — bớt 2 token, cùng kết quả).

## 2. Token tầng domain (riêng meet2note)

| Token | Giá trị | Dùng cho |
|---|---|---|
| `--color-conf-red` / `-bg` | `#dc2626` / `#fef2f2` | Badge đỏ (`confidence < 0.50`) — cũng là ngưỡng khoá export (R6) |
| `--color-conf-amber` / `-bg` | `#92400e` / `#fffbeb` | Badge vàng (`0.50–0.75`) |
| `--color-conf-green` / `-bg` | `#047857` / `#ecfdf5` | Badge xanh (`≥ 0.75`) |
| `--color-warn-bg` | `#fffbeb` | Banner `known_limitations`, item `system_generated` (O_SYS) |
| `--color-ok-bg` | `#ecfdf5` | Export thành công, gate đã mở |
| `--color-info-bg` | `#f0f9ff` | Brief (`state.brief.problem`) |
| `--color-hl-bg` / `--color-hl-border` | `#fef9c3` / `#facc15` | Turn transcript đang chiếu (R5) |
| `--color-evidence-bg` / `--color-evidence-rule` | `#f8fafc` / `#cbd5e1` | Nền + vạch trái của dòng evidence |

**Kỷ luật màu:** `primary` CHỈ dùng cho CTA. Badge semantic giữ 3 màu nhưng dạng **nền tint nhạt
+ chữ đậm** (không dùng màu chói). Màu **không bao giờ** là kênh thông tin duy nhất — badge luôn
kèm số confidence và luôn kèm nhãn chữ (xem `components.md §3`).

## 3. Spacing / radius / shadow / motion

Với Tailwind, "token khoảng cách" là **allow-list utility**, không phải biến tự đặt.
Thang: Tailwind v4 lấy `--spacing: 0.25rem` làm gốc → `gap-3` = 12px.

| Nhóm | Được dùng | Cấm |
|---|---|---|
| Spacing | `gap-1`(4) `gap-2`(8) `gap-3`(12) `gap-4`(16) `gap-6`(24) `gap-8`(32); `p-3` `p-4` `p-6` `px-3` `py-2` | giá trị lẻ `p-[13px]`, `gap-5`, `mt-7` |
| Radius | `rounded-md` (input, 8) · `rounded-lg` (card, 10) · `rounded-xl` (button, 14) · `rounded-full` (badge/pill) | `rounded-[7px]` |
| Shadow | `shadow-none` (card nghỉ — chỉ viền) · `shadow-card` (card hover) · `shadow-drawer` (sheet/popover) | shadow tự đặt inline |
| Motion | `transition-colors duration-150 ease-out`; sheet `duration-200` | `duration-1000`, animation tự phát minh |
| Focus | `focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring` — **bắt buộc mọi control tương tác** | xoá outline |

Card **hover mới** nâng shadow (kể cả `translate-y-[-1px]`), trạng thái nghỉ phẳng (chỉ viền).

## 4. Typography

- **Font:** Be Vietnam Pro (heading, weight 600–700) + Inter (body/label/evidence, 400–500–600),
  self-host `@fontsource`, **bắt buộc subset `vietnamese`**:

  ```js
  import "@fontsource/be-vietnam-pro/vietnamese-600.css";
  import "@fontsource/be-vietnam-pro/vietnamese-700.css";
  import "@fontsource/inter/vietnamese-400.css";
  import "@fontsource/inter/vietnamese-500.css";
  ```

  ⚠ Không `import "@fontsource/inter"` trần — bản đó thiếu subset `vietnamese`, dấu sẽ vỡ.
  Fallback đã khai trong `--font-heading`/`--font-sans`; đặt `font-display: swap` (mặc định của
  @fontsource) để tránh chặn render.
- **Thang cỡ chữ** (dùng đúng utility, không dùng số thô):

  | Vai trò | Utility | Cỡ |
  |---|---|---|
  | Sidebar / label / timestamp | `text-xs` | 12px |
  | Card content / thân | `text-sm` | 14px |
  | Evidence quote | `text-xs` + `leading-relaxed` | 12px/1.6 |
  | Cột `h3`, tên meeting `h2` | `text-lg` | 18px |
  | `h1` (brand) | `text-xl` | 20px |

- `leading-relaxed` (1.625) tối thiểu cho mọi text Việt — dấu stacked cần chiều cao.
- **Test dấu bắt buộc khi đổi font** (12px phải phân biệt được hỏi/ngã):

  ```
  ấ ầ ẩ ẫ ậ · ế ề ể ễ ệ · ố ồ ổ ỗ ộ · ớ ờ ở ỡ ợ · ứ ừ ử ữ ự
  ỄỘ ẲẪ ỞỮ (heading lớn)
  ```

## 5. Log đính chính (v1 → v2)

| # | v1 | v2 | Lý do |
|---|---|---|---|
| 5.1 | `--accent: #3b5bdb` là **màu thương hiệu** | đổi tên thành `--primary`; `--accent` trả về đúng nghĩa shadcn = nền hover nhạt | Trong hệ shadcn, `--accent` đã có nghĩa khác. Đặt sai tên ⇒ mọi component shadcn sai màu (ADR-0008) |
| 5.2 | `--accent-hover`, `--accent-active` | bỏ, dùng `hover:brightness-95` / `active:brightness-90` | Bớt 2 token không mang thêm thông tin |
| 5.3 | §1 tuyên bố "chỉ dùng biến" nhưng §3 spacing/radius/shadow **không có tên** | §3 chuyển thành allow-list utility Tailwind | Không thể enforce một hợp đồng không có định danh |
| 5.4 | `--hl` gộp nền + viền trong 1 token | tách `--color-hl-bg` / `--color-hl-border` | 1 biến CSS không chứa được 2 giá trị |
| 5.5 | Không nói token khai ở đâu | §0 quy định 1 chỗ + grep kiểm được | Tránh 2 nguồn sự thật với `App.css` |
| 5.6 | Font nêu tên package, không nêu path | §4 nêu path `vietnamese-*.css` + fallback + `font-display` | `import` trần sẽ mất subset `vietnamese` |
