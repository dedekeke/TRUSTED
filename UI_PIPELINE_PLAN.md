# Plan: UI pipeline kiểu GitHub Actions (Detect → Transform)

> Mục tiêu: một màn hình **Run** duy nhất. Người dùng chọn dataset (browse file hoặc chọn dataset có sẵn), chọn
> kịch bản, bấm **Run**. Các bước hiện thành **accordion** như GitHub Actions: xanh = thành công, đỏ = thất bại.
> Mở một bước ra sẽ thấy **bảng thống kê** (không phải log terminal), có so sánh với baseline của ban tổ chức.

---

> **Trạng thái (08/11):** đã implement trên branch `pet-13-pipeline-ui`. Endpoint dùng tiền tố `/api/jobs/...`
> thay cho `/api/runs/...` để giữ nguyên các endpoint cũ (và test của chúng). Chi tiết: README, mục *UI: run the pipeline*.

## 1. Hiện trạng (đã kiểm tra trên `pet-11-api-ui`)

| Phần | Hiện có | Thiếu |
|---|---|---|
| API `server/api.py` | `GET datasets, scenarios`, `POST runs` (chạy detect), `confirm`, `select`, `search` | **Transform, Evaluate**, upload file, chạy nền, trạng thái từng bước, log, tải file |
| Cách chạy | Mỗi bước là **một request đồng bộ** có `STEP_LOCK`; search mất 1–4 phút → request treo | Job chạy nền + polling |
| Chọn dataset | Chỉ chọn theo tên trong `<package>/data/` | **Browse/upload file CSV** |
| Frontend | React 19 + antd 6 + Tailwind; trang `RunDetect`, `RunPlan`; Evaluate/Benchmark dùng dữ liệu tĩnh hoặc scorecard upload | Timeline dạng accordion, bảng cho từng bước, so sánh baseline |
| Output có sẵn để hiển thị | `detect/labels.csv, spans.jsonl, linkage.json`; `select|search/decisions.json`; `transform/transform_stats.json, reports/scorecard.json, identifier_check.json`; `pipeline.json` | Chưa có endpoint đọc chúng thành JSON gọn cho UI |
| Baseline | `<package>/results/benchmark.json`: B0/B2/B2-k × 9 dataset (privacy, utility, composite, worst_reid, residual_identifiers, utility_by_scenario) và B1 detect | Chưa đưa lên UI |

Kết quả audit 27 kịch bản (07/11): chỉ **CS-S1** chạy tới transform `validated`. 16 bị `blocked` ở select
(11 vì `review_required`), 9 `target_unmet` ở search, 1 crash (EDU-S2). UI phải hiển thị tốt **cả trường hợp lỗi**.

---

## 2. Trải nghiệm người dùng

```
┌ Run #20261107-a1b2 · customer_service · CS-S1 ─────────────────── ● Thành công · 2m 14s ┐
│ ✅ 1. Input        3 bảng · 165.204 dòng · 34 cột                               0.4s  ▸ │
│ ✅ 2. Detect       34 cột: 9 direct · 6 quasi · 2 free text · 3 cần duyệt       18s   ▸ │
│ 🟡 3. Review       3 cột cần xác nhận → [Xác nhận & tiếp tục]                          ▾ │
│    ┌ bảng: table | column | nhãn detect | conf | sửa role ▼ | sửa subtype ▼ ┐           │
│ ✅ 4. Select       policy_valid · 12 giữ · 9 pseudonym · 8 tổng quát hoá · 5 xoá  2s  ▸ │
│ ✅ 5. Search       measured_ok · k≥5 đạt · utility 0.9995 · 2/50 lượt đánh giá   41s  ▸ │
│ ✅ 6. Transform    validated · 2 bảng xuất · 0 định danh sót                     35s  ▸ │
│ ✅ 7. Evaluate     privacy 0.999 · utility 0.750 · so với B2: +0.69 / −0.11        3s  ▸ │
│                                                         [⬇ Tải dữ liệu đã bảo vệ (.zip)] │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

**Màu trạng thái** (dùng chung cho header accordion và icon):

| Trạng thái backend | Màu / icon | Ý nghĩa |
|---|---|---|
| `queued` | xám ○ | chưa chạy |
| `running` | xanh dương, spinner | đang chạy |
| `ok`, `policy_valid`, `measured_ok`, `validated` | **xanh ✅** | thành công |
| `blocked`, `target_unmet`, `budget_exhausted`, `refused`, `validation_failed`, `failed`, crash | **đỏ ❌** | thất bại, kèm mã lỗi |
| `needs_review` | vàng 🟡 | chờ người dùng xác nhận (không phải lỗi) |
| `skipped` | xám, gạch | bị bỏ qua vì bước trước lỗi |

Bước lỗi **tự mở sẵn** và hiện bảng lỗi (mã lỗi, cột, lý do, gợi ý sửa). Mỗi bước có thêm một mục thu gọn
**“Raw log”** cho dev, nhưng mặc định ẩn. Người dùng đọc bảng, không đọc log.

---

## 3. Nội dung bảng của từng bước

| Bước | Thẻ số (Statistic) | Bảng chính | So sánh baseline |
|---|---|---|---|
| **1. Input** | số bảng, dòng, cột, dung lượng | file · dòng · cột · sha256 (8 ký tự) · trạng thái đọc | n/a |
| **2. Detect** | số cột theo role, số cần duyệt, số span PII | table · column · role (tag màu) · subtype · confidence (thanh) · Art.9 · cần duyệt · lý do; bảng phụ: span theo label (PERSON, PHONE…); linkage (join, khoá chủ thể) | macro-F1/sensitive recall của Detect v3 (leave-one-dataset-out, từ README) **vs B1** (`benchmark.json`); ghi rõ là số đánh giá offline, không phải đo trên lần chạy này |
| **3. Review** | số cột cần duyệt / đã duyệt | cột · nhãn detect · confidence · **dropdown sửa role/subtype** · được task nào cần | n/a |
| **4. Select** | trạng thái; đếm theo hành động (KEEP / PSEUDONYMISE / GENERALISE / REDACT / DROP) | table · column · role · hành động · method + tham số · task cần · lý do; bảng **errors/warnings** có mã (`review_required`, `unsupported_label`, …) | n/a |
| **5. Search** | trạng thái; số lượt đánh giá / budget | **Mục tiêu vs đạt được** theo bảng (k, l, t, % dưới k, dòng không rõ chủ thể); **utility theo task** vs ngưỡng; **violations**; trace (lượt · cột đổi · chấp nhận? · utility · information loss) | utility theo task **vs B2/B2-k** của cùng kịch bản (`utility_by_scenario`) |
| **6. Transform** | trạng thái gate; số bảng xuất; ô bị xoá; span đã redact | **checklist validation** (round trip, format, join, k/l/t viết lại, `pets-eval check`) ✅/❌; thống kê redaction theo label; kết quả identifier check | residual identifiers **vs B0/B2/B2-k** |
| **7. Evaluate** | privacy, utility, composite | **Bảng so sánh chính**: hàng = Ours / B0 / B2 / B2-k; cột = privacy · utility · composite · worst re-id · residual identifiers; bảng phụ: utility từng task, rủi ro từng bảng (`risk_components`) | đây chính là bảng before/after mà challenge yêu cầu |

Baseline chỉ có cho 9 dataset của package. Với dataset upload mới, cột baseline hiện “n/a” kèm tooltip giải thích.

---

## 4. Backend: thay đổi `server/api.py`

### 4.1 Mô hình chạy
- Chuyển sang **job chạy nền**: `POST /api/runs/{id}/start` trả về ngay; một worker thread chạy các bước nối tiếp,
  ghi trạng thái vào `runs/<id>/status.json` sau mỗi bước.
- **Dùng lại các hàm stage của `server/pipeline.py`** (detect → select → search → transform), không viết lại logic.
  Tách `pipeline.run()` thành danh sách step có callback `on_step(name, status, summary)`.
- Bước **Review**: nếu select trả về `review_required`, job dừng ở trạng thái `needs_review`. Sau khi người dùng gửi
  `POST /confirm`, job chạy tiếp từ Select vào **thư mục mới** (`select-2/`, `search-2/`), giữ đúng quy tắc
  “mỗi lần chạy một thư mục fresh”.
- Giữ `STEP_LOCK` cho phần nặng, nhưng request HTTP không bao giờ chờ job.

### 4.2 Endpoint

| Method | Path | Mô tả |
|---|---|---|
| GET | `/api/datasets` | (có) dataset có sẵn |
| GET | `/api/scenarios?dataset=` | (có) lọc theo dataset |
| POST | `/api/runs` | tạo run: `{dataset}` **hoặc** `{upload: true}` (chưa chạy gì) |
| PUT | `/api/runs/{id}/files/{name}.csv` | **upload một file CSV** (body thô, stream xuống đĩa; giới hạn ví dụ 200 MB/file) |
| POST | `/api/runs/{id}/start` | `{scenario | spec, budget}` → chạy nền từ Input |
| GET | `/api/runs/{id}` | trạng thái tổng + `steps[]`: `{name, status, started_at, duration_s, summary, error}` (UI poll mỗi 1–2 giây) |
| GET | `/api/runs/{id}/steps/{step}` | **dữ liệu bảng** đã chuẩn hoá cho UI (xem 4.3) |
| GET | `/api/runs/{id}/steps/{step}/log` | stdout/stderr đã bắt của bước (Raw log) |
| POST | `/api/runs/{id}/confirm` | (có) gửi nhãn đã duyệt → job chạy tiếp |
| GET | `/api/runs/{id}/download` | zip **chỉ thư mục `protected/`** |
| GET | `/api/baselines?dataset=&scenario=` | dòng B0/B2/B2-k/B1 từ `results/benchmark.json` |

Upload dùng `PUT` với body thô cho từng file, vì server chỉ dùng stdlib (module `cgi` đã bị bỏ khỏi Python 3.13+,
nên tránh multipart). Tên file được làm sạch (`[A-Za-z0-9_-]+\.csv`). Dataset upload được lưu vào `runs/<id>/data/<name>/`.

### 4.3 Chuẩn hoá output cho UI (`server/api_views.py`)
Mỗi step có một hàm `view_<step>(run_dir) -> {"stats": {...}, "tables": {"<name>": {"columns": [...], "rows": [...]}}, "issues": [...]}`:
- `detect`: đọc `labels.csv`, đếm `spans.jsonl` theo label (**chỉ đếm, không trả text**), `linkage.json`.
- `select`/`search`: đọc `decisions.json` (`columns`, `outcome`, `trace`, `errors`, `warnings`).
- `transform`: `transform_stats.json`, `manifest.json` (checks), `reports/identifier_check.json`.
- `evaluate`: `reports/scorecard.json` + baseline cùng dataset/kịch bản.

UI chỉ render `columns/rows` chung bằng một component `StepTable`, nên thêm bảng mới không cần sửa frontend nhiều.

### 4.4 Quy tắc an toàn (giữ đúng nguyên tắc hiện có của API)
- Response **không chứa giá trị ô dữ liệu gốc**: chỉ nhãn, đếm, trạng thái, digest. Raw log phải lọc qua cùng quy tắc
  (detect/LLM có thể in giá trị mẫu).
- `download` **không bao giờ** trả `evaluation/`, `rowmap_*`, `staging/`, khoá HMAC.
- Server chỉ bind `127.0.0.1`; CORS chỉ cho dev origin.
- Có giới hạn kích thước upload, timeout từng bước, và ghi lỗi vào `errors.json` (đã có).

---

## 5. Frontend (`client/`)

### 5.1 Trang và route
- Route mới `/run` (tạo run) và `/run/:id` (xem run; reload trang không mất trạng thái). Đặt làm mục đầu tiên ở Sidebar.
- Các trang cũ chạy trong browser (Detect/Protect/Evaluate tĩnh) giữ lại sau một công tắc “Demo offline”.
  Không xoá ngay để tránh rủi ro trước hạn nộp.

### 5.2 Component mới (`src/features/pipeline/`)

| Component | antd dùng | Việc |
|---|---|---|
| `DatasetSource` | `Segmented`, `Upload.Dragger` (`directory`, `multiple`, `accept=".csv"`), `Select` | 2 tab: **Browse file/thư mục** hoặc **Dataset có sẵn**; hiện danh sách file + dung lượng trước khi upload |
| `ScenarioPicker` | `Select`, `Descriptions` | lọc kịch bản theo dataset; hiện recipient, purpose, trust, targets |
| `RunTimeline` | `Collapse` | mỗi step một panel; header = icon trạng thái + tên + tóm tắt 1 dòng + thời gian |
| `StepStatusIcon` | `Badge`/icons | ánh xạ trạng thái → màu (bảng mục 2) |
| `StepPanel` | `Statistic`, `Alert`, `Tabs` | thẻ số + các bảng của step + mục “Raw log” thu gọn |
| `StepTable` | `Table` | render `{columns, rows}` chung; sort, filter, tìm kiếm; tag màu cho role/trạng thái |
| `ReviewForm` | `Table` + `Select` | sửa role/subtype các cột `needs_review` → `confirm` |
| `BaselineCompare` | `Table` | Ours vs B0/B2/B2-k; tô xanh/đỏ theo tốt hơn/kém hơn |
| `DownloadButton` | `Button` | tải zip `protected/` khi Transform `validated` |

### 5.3 Hook và service
- `useRunPolling(id)`: gọi `GET /api/runs/{id}` mỗi 1.5 giây khi còn step `running`; dừng khi xong hoặc lỗi.
- `useStepView(id, step)`: lazy-load `GET /steps/{step}` khi panel được mở lần đầu, rồi cache lại.
- Mở rộng `services/api.ts` (`backend.*`) và `types/run.types.ts` theo các endpoint mới.

---

## 6. Kiểm tra không lệch kết quả (bắt buộc)

UI/API chỉ **gọi lại code pipeline** và **đọc file kết quả**. Kết quả qua UI phải giống hệt chạy CLI.
Những gì ban tổ chức chấm (file detect `unseen`, file span `customer_service`, scorecard của `pets-eval`) vẫn
tạo bằng CLI. UI không tự tính lại số nào, chỉ đọc `reports/scorecard.json` do Transform sinh ra.

| # | Rủi ro | Kiểm tra / quy tắc |
|---|---|---|
| 1 | Tách `server/pipeline.py` thành step có callback làm đổi hành vi | **Test hồi quy** `tests/test_api_parity.py`: chạy CS-S1 bằng `python -m server.pipeline` và bằng API với **cùng khoá HMAC, release-id, model**. So sha256 của từng file trong `protected/` và trạng thái/digest trong `pipeline.json`. Phải **giống hệt**. Bản nhanh dùng dữ liệu nhỏ (như các test deploy hiện có) để chạy được trong `pytest`; bản full-data chạy tay trước khi demo. |
| 2 | Tham số mặc định API ≠ CLI | Một nguồn duy nhất cho mặc định (`budget`, `tau`, `llm`, `text_fallback`) dùng chung cho `server.pipeline` và `server.api`. Test kiểm tra hai bên bằng nhau. UI hiển thị các tham số đã dùng ở header của run. |
| 3 | Upload làm đổi byte hoặc tên dataset | Lưu nguyên byte (không đổi encoding/newline), giữ tên thư mục dataset. Test: sha256 file upload = sha256 file gốc. Pipeline vẫn tự báo `input_mismatch` nếu input bị đổi. |
| 4 | Review/confirm thay đổi kết quả | Đây là thay đổi **có chủ đích**, tương đương CLI `--confirm`, và được ghi vào provenance (`confirm_sha256`). UI hiển thị rõ “kết quả đã qua người duyệt” cùng danh sách cột đã sửa. |
| 5 | Dùng nhầm zip tải về để tự chấm | Zip chỉ có `protected/` cho bên nhận. Tự chấm vẫn dùng `evaluation/` + `rowmap_*` local (không bao giờ đưa qua API). |

**Xong khi:** `test_api_parity.py` pass trong `pytest`, và một lần chạy CS-S1 full-data cho cùng sha256 giữa CLI và UI.

---

## 7. Các giai đoạn thực hiện

| # | Việc | Ước lượng | Xong khi |
|---|---|---|---|
| 0 | Sửa bug EDU-S2 (`select.py:160`, join 3 cột) | 0.5h | 27 kịch bản không crash |
| 1 | Backend: job nền + `status.json` + `GET /runs/{id}` có `steps[]`; dùng lại stage của `server/pipeline.py`; **mặc định dùng chung + `test_api_parity.py` (mục 6)** | 4h | Chạy CS-S1 qua API, poll thấy từng bước đổi trạng thái; **sha256 `protected/` giống CLI** |
| 2 | Backend: `api_views.py` + `GET /steps/{step}` + `/log` + `/baselines` + `/download` | 3h | Đủ JSON bảng cho 7 bước; test không lộ giá trị ô |
| 3 | Backend: upload `PUT /files` + Review/confirm chạy tiếp | 2h | Upload thư mục customer_service rồi chạy; HEALTH-S1 dừng ở Review, confirm xong chạy tiếp |
| 4 | Frontend: `DatasetSource`, `ScenarioPicker`, `RunTimeline`, `StepStatusIcon`, polling | 3h | Thấy accordion xanh/đỏ cập nhật trực tiếp |
| 5 | Frontend: `StepPanel` + `StepTable` + `BaselineCompare` + `ReviewForm` + download | 4h | Mở từng step thấy bảng; Evaluate có bảng so với B0/B2/B2-k |
| 6 | Test + dọn dẹp: pytest endpoint mới; `npm run build` + lint; chạy thử CS-S1 (xanh hết) và HEALTH-S1 (vàng → xanh/đỏ) | 2h | Không lỗi; screenshot cho slide/video |

**Ưu tiên khi thiếu thời gian:** 1 (luôn gồm test parity) → 4 → 2 (chỉ Detect, Search, Evaluate) → 5 (Evaluate trước) → 3 → 6.
Bản tối thiểu để demo: chọn dataset có sẵn, accordion xanh/đỏ, bảng Evaluate so với baseline, tải zip.

---

## 8. Lưu ý và rủi ro

1. **Chỉ CS-S1 chạy xanh từ đầu đến cuối** ở thời điểm này. Bước Review (giai đoạn 3) gỡ được 11 kịch bản bị
   `review_required`. Các lỗi `target_unmet` (subject resolution) và nhánh aggregate/DP là việc của Select, nằm ngoài plan UI này.
2. **Dataset upload không có kịch bản**: kịch bản trong package gắn với tên dataset. Dataset lạ phải dùng `--spec`
   (file requirement JSON) hoặc `--no-purpose`. Bản đầu: nếu tên thư mục trùng dataset có sẵn thì cho chọn kịch bản; nếu không thì chỉ cho no-purpose.
3. **Detect model** được train trên chính 9 dataset của package. Nhãn detect trên các dataset này là in-sample. Con số F1 trên UI phải lấy từ đánh giá leave-one-dataset-out, và phải ghi rõ điều đó.
4. **File lớn** (taps 66 MB, meter 80 MB): upload stream xuống đĩa, có progress bar; không đọc cả file vào RAM ở API.
5. **Đừng hiển thị giá trị gốc** (kể cả bảng before/after) trừ khi team quyết định có chế độ preview cục bộ. Mặc định chỉ hiện thống kê.
6. **Không commit** thư mục `runs/`, model, output, `node_modules`.
7. API chạy local (`127.0.0.1`). Khi demo thì chạy `python -m server.api --model <dir> --runs <dir>` cùng `npm run dev` với `VITE_API_BASE_URL=/`.
