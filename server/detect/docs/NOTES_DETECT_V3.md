# Ghi chú sau khi implement Detect v3

> Ngày 7/11/2026. Plan: [PLAN_DETECT_V3.md](PLAN_DETECT_V3.md). Ghi chú v2: [NOTES_DETECT_V2.md](NOTES_DETECT_V2.md).
> Report: mở `out/reports_v3/index.html`. Report v1/v2 cũ (`out/reports/`) giữ nguyên, có link qua lại.

## 1. Kết quả chính

Chấm leave-one-dataset-out trên 9 dataset có nhãn. Số của v1 và v2 được chấm lại từ kết quả đã lưu, không chạy lại:

| | macro-F1, che tên cột | Recall nhạy cảm, che tên cột | macro-F1, có tên cột |
|---|---|---|---|
| v1 | 0.757 | 0.781 | **0.858** |
| v2 | 0.766 | 0.845 | 0.857 |
| **v3** | **0.774** | **0.855** | 0.854 |
| Mục tiêu trong plan | ≥ 0.766 ✅ | ≥ 0.845 ✅ | ≥ 0.858 ❌ (thiếu 0.004) |

- **Theo tiêu chí 1–2, v3 tốt hơn v2.** F1 khi che tên cột chênh dưới 0.01, nên recall nhạy cảm quyết định, và v3 cao hơn.
- **Theo tiêu chí 3 (kiểm tra bằng mắt trên `unseen`), v3 kém v2.** v3 đổi c13 (mã công đoàn AY-PS/AY-HL, dữ liệu Art. 9) và c25 (số giờ) thành `non_sensitive`, trong khi v2 đánh dấu cả hai là cần bảo vệ.
- **Khuyến nghị:** dùng v3 làm detector chính, nhưng **file nộp `unseen` nên dùng của v2** (`out/v2/unseen_field_labels.csv`), vì bỏ sót cột công đoàn là lỗi nặng. Bạn và team quyết định; file của v3 nằm ở `out/v3/unseen_field_labels.csv`.

**6 cột sai ở `health.ed_visits` (che tên cột):**

| Cột | v2 | v3 |
|---|---|---|
| `triage` | sai | **đúng** |
| `readmit_30d` | sai | **đúng** |
| `disposition` | sai, confidence 0.87, không bị gắn cờ | vẫn sai, nhưng **được gắn cờ "review"** (0.59) |
| `temp_c` | sai, được gắn cờ | vẫn sai, được gắn cờ |
| `arrival_mode` | sai | vẫn sai (B6 chưa làm) |
| `ambulance_unit` | sai | vẫn sai (B5 đã bỏ, xem mục 2) |

## 2. Đã giữ và đã bỏ gì (theo ablation, luật: không được làm giảm F1 ở chế độ nào)

| Thay đổi | Kết quả | Quyết định |
|---|---|---|
| **Router chọn kNN hay LogReg cho từng cột** | Có tên cột 0.852 (bằng kNN), che tên cột 0.760 (bằng LogReg). Router lấy được phần tốt nhất của mỗi bên | ✅ Giữ |
| Margin giảm theo `name_info` | F1 không đổi, recall giảm 1 điểm | ❌ Bỏ |
| **B1: phân bố giá trị cho LLM** | Che tên cột tăng từ 0.760 lên 0.774 | ✅ Giữ |
| **B2: confidence trung thực** | F1 không đổi; số cột sai mà không bị gắn cờ giảm từ 43 xuống 27 (có tên cột) và từ 65 xuống 42 (che tên cột) | ✅ Giữ |
| B3: LLM được nâng cột lên sensitive trong bảng Art. 9 | Có tên cột −0.010 | ❌ Bỏ |
| B4: nới recall margin trong bảng Art. 9 (0.20 và 0.25) | Giảm ở cả hai chế độ | ❌ Bỏ |
| B5: siết rule HOSTNAME | **Không làm.** Hostname thật trong `cyber` (`LT-GORHIE-2274`) có cùng dạng viết hoa với mã xe cấp cứu (`AU-TKU-13`), nên rule mới sẽ làm hỏng 5 cột đang đúng | ❌ Bỏ |
| B6, A3 (tuỳ chọn) | Chưa làm | – |

Chi tiết từng bước nằm ở `out/compare_v3/ablation.csv` và `out/compare_v3/ablation_llm.csv`, và cũng có trong `index.html`.

## 3. Những chỗ làm khác plan (cần nói thật khi trình bày)

1. **Công thức `name_info` được sửa sau khi xem kết quả ablation đầu.** Bản đầu đòi token của tên phải có trong từ vựng lấy từ các dataset khác. Nhưng những tên rõ nghĩa như `intent`, `sentiment`, `csat` chỉ xuất hiện ở một dataset, nên bị chấm 0.15 và router đẩy chúng sang LogReg (có tên cột chỉ đạt 0.807). Bản hiện tại: tên dạng mã thì 0, tên là từ thật thì tối thiểu 0.7.
2. **Router cuối đơn giản hơn plan:** còn ngữ cảnh tên (tên cột **hoặc** tên bảng) thì dùng kNN, không còn tên nào thì dùng LogReg. Ở chế độ mixed, kNN thắng bản trộn 50/50 (0.810 so với 0.796), vì kNN dùng được tên bảng ngay cả khi tên cột đã bị che. Hệ quả: **ở chế độ mixed, router của v3 chỉ bằng "luôn dùng kNN" chứ không vượt được** (mục tiêu trong plan chưa đạt). Router chỉ khác kNN khi cả tên bảng cũng bị che.
3. **Phát hiện và sửa một chỗ lộ thông tin trong bản nháp v3:** `blind()` của v1 chỉ che tên cột, còn tên bảng vẫn giữ. Ở chế độ che hoàn toàn, kNN của v3 nhìn thấy tên bảng nên điểm cao giả tạo (0.738 so với 0.730 của v1). Đã sửa: chế độ che hoàn toàn của v3 che cả tên bảng. Số v3 trong bảng trên là số sau khi sửa.
4. **Bước 9 (chạy lại span và linkage với nhãn v3):** chạy vào thư mục riêng `out/spans_v3/` và `out/linkage_v3/`, không ghi đè kết quả cũ. Kết quả span **không đổi** (F2 0.998).

## 4. Điểm yếu mới của v3

- **kNN tin đuôi `_name` quá mức.** Khi có tên cột, v3 gán thêm 4 cột không phải tên người thành `PERSON_NAME`: `rule_name`, `subject_name`, tên trạm xe đạp và tên điểm dừng xe buýt. Select sẽ xoá hoặc pseudonym hoá thừa các cột này. Nhờ các cột đó, từ điển tên dùng cho span có thêm tên địa điểm, nhưng điểm span không bị ảnh hưởng.
- **Khi có tên cột, v3 giảm ở `customer_service` (−0.020 so với v2) và `education` (−0.046 so với v2)**, do kNN thay cho LogReg-có-tên-cột của v2. Ngược lại, `finance` tăng (0.880, cao nhất trong 3 bản).
- **`cyber`, `smart_city`, `public_admin` vẫn kém v1** khi che tên cột, vì v3 không sửa vấn đề bảo vệ thừa của v2 ở các dataset này.
- **LLM có thể đoán sai domain của bảng.** Ở chế độ che tên cột, LLM đoán `health.ed_visits` là "employees", trong khi bảng nói về bệnh nhân. Nhiều khả năng do có cột tên và mã bác sĩ (`STAFF-…`). Domain sai làm LLM trả lời sai cho các cột khác trong bảng; đây có thể là một lý do khiến B3 và B4 (vốn dựa vào domain) không giúp được. Domain của từng bảng được ghi ở đầu mỗi nhóm trong report v3 để kiểm tra.
- **Chọn tham số trên cùng 9 dataset dùng để chấm.** Mỗi lần ablation là một lần nhìn đáp án, nên các mức tăng nhỏ (dưới 0.01) có thể không giữ được trên dữ liệu mới. Bài test độc lập duy nhất là nhãn ẩn của `unseen`, mà trên đó v3 có dấu hiệu kém v2.

## 5. Gợi ý bước tiếp

1. **Chọn file nộp `unseen`:** v2 hay v3. Mình nghiêng về v2, vì v2 bắt được cột công đoàn.
2. **Sửa lỗi `_name` của kNN:** nếu cột có đuôi `_name` nhưng giá trị không giống tên người (rule tầng 1 `PERSON_NAME` không khớp, ít `first_name`), thì không nhận là `PERSON_NAME`. Cần chạy lại ablation để đo.
3. **Nếu muốn đạt mục tiêu "có tên cột ≥ 0.858":** thử trộn kNN với LogReg-có-tên-cột (bản của v2) cho các cột có tên rõ, thay vì chỉ dùng kNN.
4. **Báo cho người làm Select:** nhãn v3 nằm ở `out/compare_v3/pred_v3_names.csv`. File này có thêm các cột `name_info`, `tier2_used`, `art9_table`, và `needs_review` giờ đáng tin hơn (cột sai mà không bị gắn cờ ít hơn khoảng 37%).

## 6. Lệnh (chạy trong `server/detect`)

```bash
python3 -m pets_detect_v3 ablation      # router / margin, không LLM (khoảng 1 phút)
python3 -m pets_detect_v3 compare       # chỉ chạy v3, đọc v1/v2 đã lưu -> out/reports_v3/ (LLM có cache thì khoảng 2 phút)
python3 -m pets_detect_v3 report        # dựng lại HTML
python3 -m pets_detect_v3 unseen        # out/v3/unseen_field_labels.csv
python3 -m unittest discover -s tests   # 42 test
```
