# Giao thức Đánh giá Giá trị Sản phẩm cho Cố vấn (Product/User Value Evaluation Protocol)

> **Phiên bản:** 1.0 (2026-11-23)
> **Task liên quan:** `AI-07` (**AIE** chủ trì, phối hợp **SWE2** & **MLOPS**)
> **Mục tiêu:** Đáp ứng tiêu chí **Product/User Value** trong Đề bài Chủ đề 4 §4 và nguyên lý **4. Product Boundary** của **CMU MLIP (Lectures 1–2)**: chứng minh bằng thực nghiệm có kiểm soát rằng LearnGuard mang lại giá trị thực tế cho cố vấn học tập thay vì chỉ có điểm offline trên mô hình.

---

## 1. Câu hỏi Thực nghiệm (Research Questions)

1. **RQ1 (Efficiency — Tiết kiệm Thời gian):** Việc sử dụng LearnGuard (`Risk Score + Uncertainty + Linear SHAP + Advisor Brief`) có giúp cố vấn hoàn thành rà soát và đưa ra quyết định hỗ trợ cho mỗi sinh viên **nhanh hơn đáng kể** so với việc tự đọc số liệu LMS/bài nộp thô không?
2. **RQ2 (Decision Quality & Guideline Alignment — Chất lượng Tư vấn):** Quyết định và nội dung hỗ trợ của cố vấn khi dùng LearnGuard có **đầy đủ bằng chứng và bám sát `advisor_guidelines.md`** hơn so với khi không có AI hỗ trợ không?
3. **RQ3 (Appropriate Trust — Tin cậy Có kiểm soát, Không Over-Trust):** Trên các ca `manual_review`, `insufficient_data` và `fallback_review`, cố vấn có nhận diện được giới hạn của AI (chỉnh sửa hoặc từ chối khi cần) thay vì bấm chấp nhận mù quáng không?

---

## 2. Thiết kế Thí nghiệm Đối chứng (Controlled Study Design)

### 2.1. Tập 10 Case Studies Chuẩn hóa (Lấy từ `validation` `2014B` — Cấm đụng `holdout` `2014J`)
Chọn cố định **10 hồ sơ sinh viên ẩn danh** (`student_key` 16-hex) thuộc nhiều học phần (`AAA`..`GGG`) từ tập `validation` (`2014B`), phân tầng đại diện đầy đủ các trạng thái vận hành thực tế:

| Nhóm Ca | Số lượng | Đặc điểm Dữ liệu tại `cutoff_day = 27` | Mục tiêu Kiểm chứng |
| :--- | :---: | :--- | :--- |
| **Nhóm 1: `scored` — Rủi ro Cao (Top-20%)** | **4 ca** | Tín hiệu rõ (tụt click tuần 3–4, trễ/thiếu bài TMA đầu kỳ, đa dạng `code_module`). | Đo tốc độ nhận diện nguyên nhân & lập kế hoạch hỗ trợ bám sát hướng dẫn. |
| **Nhóm 2: `scored` — Cận biên / Trung bình** | **2 ca** | `risk_score` sát ngưỡng `0.810348` hoặc tín hiệu trái chiều (click cao nhưng điểm thấp). | Đo khả năng cân nhắc đa chiều của cố vấn thay vì chỉ nhìn nhãn. |
| **Nhóm 3: `manual_review` (`uncertainty >= 0.80`)** | **2 ca** | Xác suất dự đoán vùng xám (`0.40–0.60`), độ bất định cao. | Kiểm tra cố vấn có đọc cảnh báo bất định và tự thẩm định kỹ hơn không. |
| **Nhóm 4: `insufficient_data`** | **1 ca** | `0` click và `0` bài nộp trước ngày 27. | Kiểm tra cố vấn có tránh kết luận vội vàng khi thiếu dữ liệu LMS không. |
| **Nhóm 5: `fallback_review` (Giả lập LLM sập)** | **1 ca** | LLM chính lỗi → hệ thống xuất brief mẫu từ SHAP signals thật. | Đo tính hữu ích tối thiểu của giao diện ngay cả khi mất dịch vụ LLM. |

### 2.2. Hai Điều kiện Đối chứng (Baseline Control vs Treatment)
Áp dụng thiết kế **Within-Subjects Counterbalanced** với tối thiểu **2 người đóng vai cố vấn** (thành viên nhóm không trực tiếp viết code sinh brief cho ca đó, sử dụng `advisor_guidelines.md` làm chuẩn):

- **Điều kiện A — Control (Không có LearnGuard AI):**
  - Cố vấn chỉ nhận bảng số liệu thô 4 tuần (`clicks` theo tuần, điểm các bài nộp, `insufficient_data` flag) dưới dạng bảng/CSV + tài liệu `advisor_guidelines.md`.
  - **Không** có `risk_score`, **không** có Linear SHAP, **không** có Advisor Brief / Chatbot.
  - Cố vấn tự đọc, tự tổng hợp lý do rủi ro và viết 1–2 hành động hỗ trợ đề xuất.
- **Điều kiện B — Treatment (Có LearnGuard Platform):**
  - Cố vấn sử dụng giao diện `StudentDetailPage` trên LearnGuard (hoặc bản xuất tương đương gồm `Risk Score + Uncertainty`, `Top 5 SHAP Signals`, `4-Week Activity Chart`, `Advisor Brief`, nút `Edit / Accept / Reject + Feedback`, và `AdvisorChatDrawer`).
  - Cố vấn rà soát brief, chỉnh sửa hoặc từ chối nếu chưa đạt, nhập `feedback`, và chốt quyết định hỗ trợ.
- **Cơ chế Chống Nhiễu Thứ tự (Counterbalancing):**
  - Chia 10 ca thành 2 bộ tương đương (`Set X`: 5 ca, `Set Y`: 5 ca).
  - Người đánh giá 1 làm `Set X` theo Điều kiện A rồi `Set Y` theo Điều kiện B; Người đánh giá 2 làm `Set Y` theo Điều kiện A rồi `Set X` theo Điều kiện B.

---

## 3. Bộ Chỉ số Đo lường & Rubric Chấm điểm

### 3.1. Chỉ số Định lượng
1. **Thời gian xử lý mỗi hồ sơ (`review_duration_sec`):** Bấm giờ từ lúc mở hồ sơ đến khi chốt xong phương án hỗ trợ. Tính **Trung vị (Median)**, **Trung bình (Mean)** và **Tỷ lệ giảm thời gian (`% Time Reduction`)**.
2. **Tỷ lệ Can thiệp của Con người (`Human Oversight Action Rate`):** Trên Điều kiện B, thống kê tỷ lệ `accepted` nguyên bản, `edited + accepted`, và `rejected` (đặc biệt trên nhóm `manual_review` và `fallback_review`).
3. **Số lượt hỏi thêm qua Chat Copilot** (nếu sử dụng trong Treatment).

### 3.2. Rubric Chất lượng Quyết định (Thang 0–5, Chấm Độc lập)
Hai người đánh giá chéo chấm kết quả đầu ra cuối cùng của từng ca (cả Control và Treatment) theo 4 tiêu chí (tổng 0–5 điểm quy đổi):
1. **Đúng Dữ liệu (Grounded Accuracy — 0..1.5đ):** Có nêu đúng các sự kiện click/bài nộp thực tế trước ngày 27 không?
2. **Bám sát Hướng dẫn (`advisor_guidelines.md` Alignment — 0..1.5đ):** Gợi ý hỗ trợ có cụ thể, khả thi và đúng quy trình cố vấn không?
3. **An toàn Phi nhân quả (Non-Causal & No-PII Safety — 0..1.0đ):** Không khẳng định nhân quả chắc chắn, không phán xét tâm lý/đạo đức sinh viên, không lộ PII.
4. **Nhận thức Bất định (Uncertainty Awareness — 0..1.0đ):** Có thận trọng với các ca `manual_review` / `insufficient_data` / `fallback_review` không?

---

## 4. Tiêu chí Thành công (Acceptance Criteria cho `AI-07`)

Thử nghiệm được coi là đạt chuẩn bảo vệ đồ án khi báo cáo đầu ra (`docs/reports/product-value-evaluation.md` trong `Data-ML-MLOPS` hoặc `docs/06-testing/`) chứng minh đủ 4 điểm:
1. Có đủ bảng dữ liệu thô **20 lượt đánh giá** (10 ca × 2 điều kiện, có `student_key`, thời gian, quyết định và điểm rubric).
2. Thời gian rà soát trung vị ở Điều kiện B **giảm `>= 30%`** so với Điều kiện A.
3. Điểm chất lượng quyết định trung bình ở Điều kiện B **cao hơn hoặc tối thiểu tương đương** Điều kiện A (`>= 4.0 / 5.0`), và **0 vi phạm an toàn phi nhân quả**.
4. Ghi nhận được bằng chứng **Human Oversight thực chất** (cố vấn có thao tác chỉnh sửa/từ chối hoặc để lại `feedback` ở các ca cận biên/`manual_review`/`fallback_review` thay vì `100% Accept` máy móc).

---

## 5. Mẫu Nhật ký Ghi nhận Kết quả (Experiment Log Template)

```markdown
| Case # | student_key | Category | Evaluator | Condition (A: No AI / B: LearnGuard) | Duration (sec) | Action (Write / Accept / Edit+Accept / Reject) | Quality Score (0-5) | Non-Causal Safe? (Y/N) | Notes / Feedback |
| :--- | :--- | :--- | :--- | :---: | :---: | :--- | :---: | :---: | :--- |
| 01 | `a1b2...` | `scored_high` | Eval-1 | A (Control) | ... | Manual Note | ... | Y | ... |
| 01 | `a1b2...` | `scored_high` | Eval-2 | B (LearnGuard) | ... | Edit + Accept | ... | Y | ... |
```
