# Ghi chú sau khi implement Detect v2

> Ngày 7/11/2026. Plan gốc: [PLAN_DETECT_V2.md](PLAN_DETECT_V2.md). README tiếng Anh cho repo: [README_V2.md](README_V2.md).

## 1. Đã làm gì

| Phần trong plan | Trạng thái | Ở đâu |
|---|---|---|
| Bước 1: enhance detector (v2) | Xong | `pets_detect_v2/` (`features.py`, `classifier.py`, `table_llm.py`, `pipeline.py`) |
| Bước 4: chạy v1 và v2, xuất report HTML | Xong | `out/reports/index.html`, mỗi dataset 2 file `<dataset>_v1.html` và `<dataset>_v2.html` |
| Chọn bản nền | **v2** | Ghi trong khung xanh ở đầu `index.html` |
| Bước 7a: PII span trong free text | Xong | `pets_detect_v2/spans/`, report `<dataset>_spans.html` |
| Bước 7b: linkage | Xong | `pets_detect_v2/linkage.py`, `out/linkage/<dataset>.json`, có thêm một mục ở cuối các report v2 |
| Unit test | 22 test mới, đều pass. Test của v1 vẫn pass (tổng 30 test) | `tests/test_detect_v2.py`, `tests/test_spans.py` |

**Không sửa file nào của v1** (`pets_detect/`). v2 chỉ import profiler, patterns và rules của v1.

**Mở report:** mở thẳng `server/detect/out/reports/index.html` bằng trình duyệt. Report chỉ dùng HTML + CSS, chạy offline được.

## 2. Kết quả chính

### Detect cấp cột

Chấm leave-one-dataset-out bằng `pets_eval`, trên 9 dataset có nhãn:

| | macro-F1, che tên cột | Recall nhạy cảm, che tên cột | F1 `sensitive_attribute`, che tên cột | macro-F1, có tên cột |
|---|---|---|---|---|
| B1 (ban tổ chức) | – | – | – | 0.646 |
| v1 (session "Read challenge") | 0.757 | 0.781 | 0.130 | **0.858** |
| **v2** | **0.766** | **0.845** | **0.386** | 0.857 |

- **v2 thắng theo tiêu chí trong plan.** macro-F1 khi che tên cột chênh dưới 0.01, nên xét tiếp recall nhạy cảm, và v2 cao hơn 6.4 điểm.
- **Điểm cải thiện lớn nhất:** F1 của `sensitive_attribute` khi che tên cột tăng từ 0.13 lên 0.39. Đây chính là điểm yếu mà v1 không giải được.
- **Trên `unseen`:** v2 đánh dấu lương, phụ cấp, giờ làm, mã công đoàn và nơi làm việc là cần bảo vệ, trong khi v1 để `non_sensitive` hết. Cả hai đều bỏ sót cột nghề nghiệp (c22).
- **File nộp `unseen` của v2:** `out/v2/unseen_field_labels.csv`.

### Span PII trong free text

Chấm trên 20% bản ghi giữ lại làm tập test, so với B2:

| | F2 tổng | Recall PERSON/PHONE/ADDRESS/NATIONAL_ID |
|---|---|---|
| B2 regex (ban tổ chức) | 0.184 | 0.142 |
| Chỉ regex + số đọc bằng miệng của v2 | 0.219 | 0.146 |
| v2 không dùng từ điển tên lấy từ dữ liệu | 0.998 | 0.998 |
| **v2 đầy đủ** | **0.998** | **0.999** |

- Đạt mục tiêu recall ≥ 0.95 của HEALTH-S1 trên mọi file.
- **File yếu nhất là `customer_service` turns** (recall 0.962). Các loại bị bỏ sót nhiều nhất: ACCOUNT_NUMBER (26/159), DATE (15/115), NATIONAL_ID (13/174), thường do identifier bị tách qua hai lượt nói.
- **File nộp cho tập `eval` ẩn của ban tổ chức:** `out/spans/pets_submission/customer_service_eval_spans.jsonl` (34.833 lượt nói, có `entity_id`).

### Linkage

Mỗi dataset có các thông tin sau:
- **Khoá join** cần pseudonym nhất quán. Ví dụ `clinical_notes.visit_id` và `lab_results.visit_id` trỏ tới `ed_visits.visit_id`.
- **Identifier xuất hiện ở dataset khác.** Ví dụ tên trong `health` cũng có trong `customer_service`, `finance`, `mobility`.
- **Thông tin ẩn trong ID:** HETU chứa ngày sinh và giới tính.
- **Tỉ lệ dòng có k<5 trên các QI đã phát hiện**, kèm cột gây rủi ro nhất. Ví dụ với `health.ed_visits`, sau khi làm thô mặc định vẫn còn 94% dòng có k<5. Cột gây rủi ro nhất là `date_of_birth`: bỏ cột này đi thì chỉ còn 3%.

## 3. Những chỗ làm khác plan (cần biết khi trình bày)

1. **LLM theo bảng chuyển sang 2 giai đoạn.** Bản đầu gán nhãn khoảng 11 cột trong một lần gọi, nhưng `qwen2.5:7b` bị lẫn cột: lương bị gán thành IBAN, mã công đoàn thành biển số. Bản hiện tại làm như sau:
   - mỗi bảng gọi 1 lần để hỏi bảng nói về gì, chủ thể là ai;
   - sau đó mỗi cột chưa chắc gọi 1 lần ngắn, có kèm domain và tóm tắt các cột khác;
   - cột chưa chắc không được xem phỏng đoán có sẵn, vì model 7B có xu hướng chỉ "đồng ý" với phỏng đoán đó.
2. **LLM chỉ làm trọng tài.** Thay đổi này được thêm **sau lần so sánh đầu tiên**.
   - Ở lần chạy đầu, v2 có LLM khi che tên cột chỉ đạt 0.741, **thấp hơn** cả v2 không có LLM (0.760). LLM đổi 22 nhãn đúng thành sai, chỉ sửa được 17 nhãn sai thành đúng; lỗi chủ yếu là gán bừa `technical_identifier`.
   - Luật mới: LLM chỉ được đổi sang role mà classifier cho xác suất ≥ 0.15. Mình chỉ thử đúng một giá trị, không dò nhiều giá trị.
   - Kết quả lần chạy đầu được lưu ở `out/compare/run1/` để minh bạch.
3. **Subtype do LLM đề xuất bị lọc.** Model 7B chọn subtype rất tuỳ tiện (lương thành `GPS_COORDINATE`), nên chỉ nhận subtype khi cặp (role, subtype) có trong catalog và giá trị khớp pattern. Nếu không thì lấy subtype từ classifier.
4. **Classifier:** dùng xác suất gốc của logistic regression, không thêm bước calibration riêng, vì nhiều class quá ít mẫu cho cross-validation. GBM đã thử nhưng không được chọn: chậm hơn khoảng 20 lần và F1 `sensitive_attribute` thấp hơn.
5. **Số đọc bằng miệng:** tìm thẳng chuỗi từ chỉ số trên text gốc, thay vì chuẩn hoá rồi map vị trí ngược lại như plan. Cách này đơn giản hơn và không bao giờ lệch vị trí.
6. **DATE được chuyển từ regex sang tagger. Thay đổi này cũng làm sau khi đã thấy kết quả test:** regex DATE gây 1.068 span sai trong `finance`, vì ngày trong tin nhắn chuyển khoản không được gán nhãn PII. Điểm trên tập dev cũng tăng (0.994 lên 0.999), nên quyết định này có cơ sở ngoài tập test. Dù vậy, cần nói thật là mình đã nhìn số test trước khi sửa.
7. **Chưa dùng LLM cho span.** Không cần, vì tagger đã đạt F2 0.998.

## 4. Điểm yếu và rủi ro còn lại (nên nói trên slide)

- **v2 kém v1 ở `cyber` (−0.10), `smart_city` (−0.06) và `public_admin` (−0.05)** khi che tên cột. Nguyên nhân: classifier cộng recall bias gán một số cột log mạng vô hại (số byte, bộ đếm) thành nhạy cảm. Đây là đánh đổi có chủ ý (bảo vệ thừa còn hơn bỏ sót), nhưng sẽ làm Select bảo vệ thừa ở các dataset đó.
- **Độ chính xác subtype khi che tên cột thấp hơn v1** (0.688 so với 0.741).
- **Con số span rất cao vì text synthetic được sinh từ template.** Trên text thật, điểm sẽ thấp hơn. Nếu tính khớp chính xác vị trí thì điểm thấp hơn ở một số file: `chief_complaint` chỉ 0.38, do span lệch đuôi biến cách tiếng Phần Lan; `cyber` 0.86. `pets_eval` mặc định chấm theo kiểu chồng lấn.
- **Từ điển tên lấy từ chính các cột tên trong dữ liệu.** Điều này hợp lý (công ty có sổ khách hàng của mình), nhưng nên nói rõ. Bản không dùng từ điển cũng đạt F2 0.998, nên kết quả không phụ thuộc vào nó.
- **"Identifier dùng chung" trong linkage** có thể bao gồm tên trùng ngẫu nhiên giữa hai người khác nhau. Đây là tín hiệu rủi ro, không phải bằng chứng là cùng một người.
- **Rule theo tên cột của cả v1 và v2 được viết sau khi đọc catalog**, nên điểm "có tên cột" lạc quan. Chỉ điểm che tên cột và nhãn ẩn của `unseen` mới là bài test thật.
- **Thời gian trong report là thời gian khi đã có cache.** Lần chạy đầu không cache: LLM của v2 mất khoảng 15 phút cho cả 10 dataset ở 2 chế độ (226 lần gọi, máy M4 Pro). Còn v1 đã có cache từ trước.

## 5. Cần làm hoặc quyết định tiếp

1. **Báo cho người làm Select:**
   - **Nhãn cột:** `out/compare/pred_v2_names.csv`. Các trường quan trọng: `privacy_role`, `subtype`, `art9`, `needs_review`, `table_domain`, `confidence`, `reason`.
   - **Span:** `out/spans/pred_test_*.jsonl` (định dạng giống `metadata/pii_spans`, thêm `confidence`). Nếu Select cần span cho **toàn bộ** bản ghi, mình cần thêm một lệnh chạy trên cả dataset; hiện mới có tập test và tập `eval`.
   - **Linkage:** `out/linkage/<dataset>.json`.
2. **Quyết định của cả team:** `out/` và `pets_submission/` chứa giá trị PII thật của dữ liệu synthetic. Trước khi đưa file nộp lên repo public, cần thống nhất với cả team. `out/` đã nằm trong `.gitignore`.
3. **Nộp cho ban tổ chức chấm ẩn:** copy `out/v2/unseen_field_labels.csv` (đổi tên thành `unseen_field_labels.csv`) và `out/spans/pets_submission/customer_service_eval_spans.jsonl` vào thư mục `pets_submission/` của repo.
4. **Nếu còn thời gian:** sửa lỗi bảo vệ thừa ở `cyber`, bằng cách chỉ áp recall bias khi bảng có tín hiệu là bảng về người. Cần chạy lại `compare` để đo.

## 6. Lệnh hay dùng (chạy trong `server/detect`)

```bash
python3 -m pets_detect_v2 compare      # v1 vs v2 + report (LLM có cache thì khoảng 15 giây)
python3 -m pets_detect_v2 spans        # span: train, chấm, file nộp (khoảng 3 phút)
python3 -m pets_detect_v2 linkage      # linkage (vài giây)
python3 -m pets_detect_v2 report       # dựng lại HTML từ kết quả đã lưu
python3 -m pets_detect_v2 unseen       # file nộp unseen
python3 -m unittest discover -s tests  # test
```
