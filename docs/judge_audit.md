# Judge audit

Chạy trong `src/`:
- `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5`
- `python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5`

Quy ước lớp dương tính: `POS = "FAIL"` (mục tiêu của judge là phát hiện các phản hồi lỗi). Ngưỡng đạt FLOORS: `κ ≥ 0.6`, `Precision ≥ 0.8`, `Recall ≥ 0.7`.

## Bảng hiệu chỉnh (Calibration comparison)

| Tiêu chí | CSV nguồn | n | κ | Precision | Recall | Specificity | Ma trận nhầm lẫn (tp/fp/fn/tn) | Fail rate (observed → Rogan-Gladen) | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|---|---|---|---|
| `tone_ok` | `data/eval/judge_tone_public.csv` | 100 | 0.757 | 0.857 (24/28) | 0.800 (24/30) | 0.943 (66/70) | tp=24, fp=4, fn=6, tn=66 | 0.280 → 0.300 | **PASS** (0.757≥0.6, 0.857≥0.8, 0.800≥0.7) | **dùng** (cho tiêu chí giọng điệu, kèm sửa nhãn `H-081` & siết rubric) |
| `helpful` | `data/eval/judge_helpful_public.csv` | 100 | 0.375 | 1.000 (9/9) | 0.300 (9/30) | 1.000 (70/70) | tp=9, fp=0, fn=21, tn=70 | 0.090 → 0.300 | **FAIL** (κ=0.375<0.6, R=0.300<0.7) | **loại** (cấm dùng làm judge hoặc CI gate) |

Chi tiết kiểm tra phụ cho `tone_ok`: `p_o = 0.900`, `p_e = 0.588`, tỉ lệ lỗi thực theo nhãn người = `30/100 = 0.300` (khớp với Rogan-Gladen `0.300`). Với `helpful`: `p_o = 0.790`, `p_e = 0.664`, judge chỉ phát hiện `9/30` lỗi (`observed_fail_rate = 0.090`), bỏ sót `21/30` lỗi (`70%` false negative) dù tỉ lệ lỗi hiệu chỉnh Rogan-Gladen là `0.300`.

## Audit thủ công các bất đồng (13 case từ cả hai CSV)

| # | Nguồn CSV | Case | Reply (trích) | Judge nói | Người nói | Ai đúng? | Ghi chú & Hành động sửa rubric / quy trình |
|---|---|---|---|---|---|---|---|
| 1 | `judge_tone_public.csv` | `H-008` | `"Em đã hoàn tiền cho anh rồi nha, anh check giúp em."` | `PASS` | `FAIL` | **Người** | Xưng `"em"` + `"nha"` quá suồng sã với khách; judge nhầm sang "thân thiện". **Sửa rubric:** cấm đại từ thân mật (`em`, `nha`, `nhé`), yêu cầu chuẩn `LogiX` / `anh/chị` + `ạ`. |
| 2 | `judge_tone_public.csv` | `H-017` | `"Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha."` | `PASS` | `FAIL` | **Người** | Xưng `"bạn"` + `"rồi nha"` thiếu trang trọng với khách lớn tuổi; judge đánh giá nhầm là thân thiện. **Sửa rubric:** đưa xưng hô `"bạn"` và từ đệm `"rồi nha"` vào negative examples bắt buộc phạt `FAIL`. |
| 3 | `judge_tone_public.csv` | `H-029` | `"Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm."` | `PASS` | `FAIL` | **Người** | Giọng ra lệnh (`"không cần nhắn thêm"`), nhưng judge chỉ nhìn từ mở đầu `"Dạ, vui lòng"`. **Sửa rubric:** chấm theo toàn câu, phạt `FAIL` mọi câu có mệnh lệnh/ngăn khách phản hồi bất kể có `"Dạ"`. |
| 4 | `judge_tone_public.csv` | `H-042` | `"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."` | `FAIL` | `PASS` | **Người** | Ngắn gọn nhưng lịch sự và đủ ý; judge phạt oan vì `"thiếu xin lỗi"`. **Sửa rubric:** chỉ yêu cầu xin lỗi khi từ chối, chậm trễ hoặc sự cố; thông báo hoàn tiền thành công ngắn gọn vẫn `PASS`. |
| 5 | `judge_tone_public.csv` | `H-051` | `"Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ."` | `FAIL` | `PASS` | **Người** | Dùng từ `"refund"` nằm trong từ vựng CS LogiX cho phép; judge phạt nhầm do có từ tiếng Anh. **Sửa rubric:** bổ sung whitelist thuật ngữ CS được phép (`refund`, `claim`, `order`). |
| 6 | `judge_tone_public.csv` | `H-063` | `"Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ."` | `PASS` | `FAIL` | **Người** | Hứa `"sẽ hoàn thêm"` ngoài kết quả hệ thống nhưng giọng vẫn lễ phép nên judge bỏ qua. **Sửa rubric:** cấm cam kết/hứa hẹn ngoài kết quả thực thi; tách kiểm tra tính xác thực sang code/trace check. |
| 7 | `judge_tone_public.csv` | `H-070` | `"Dạ, LogiX đã hoàn 90.000đ cho đơn O-909 ạ 😂😂"` | `PASS` | `FAIL` | **Người** | Dùng emoji cười (`😂😂`) không phù hợp ngữ cảnh khiếu nại. **Sửa rubric:** cấm emoji cợt nhả trong mọi phản hồi xử lý khiếu nại/hoàn tiền. |
| 8 | `judge_tone_public.csv` | **`H-081`** | `"Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ."` | `FAIL` | `PASS` | **Judge đúng (nhãn người sai)** | **Nhãn người sai** do annotator đọc nhầm ticket; judge bắt đúng `FAIL`. **Hành động:** sửa nhãn gốc `H-081` thành `FAIL` và bổ sung bước double-check nhãn người trước khi tính calibration tiếp theo. |
| 9 | `judge_tone_public.csv` | `H-088` | `"Dạ, dạ, LogiX đã hoàn 40.000đ cho đơn O-233 ạ."` | `FAIL` | `PASS` | **Người** | Lặp `"Dạ, dạ"` là lỗi gõ nhẹ, người chấp nhận; judge quá nhạy. **Sửa rubric:** phân biệt lỗi gõ nhẹ không ảnh hưởng thái độ với vi phạm giọng điệu. |
| 10 | `judge_tone_public.csv` | `H-094` | `"Da, LogiX da hoan 40.000đ cho don O-341, xin loi vi su bat tien."` | `PASS` | `FAIL` | **Người** | Văn bản mất dấu tiếng Việt (lỗi dịch máy/encoding), nhưng judge vẫn hiểu ngữ nghĩa nên cho qua. **Hành động:** thêm kiểm tra code (regex/Unicode dấu tiếng Việt) trước khi gọi judge. |
| 11 | `judge_helpful_public.csv` | `HL-015` | `"Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ."` | `PASS` | `FAIL` | **Người** | **Sai tiền:** reply báo `55.000đ` nhưng ledger chỉ ghi `40.000đ`. Judge chỉ đọc reply text, không có ledger nên không thể phát hiện. **Hành động:** loại judge `helpful`, thay bằng code grader đối chiếu số tiền trong reply với `refund_ledger` (FM-08). |
| 12 | `judge_helpful_public.csv` | `HL-016` | `"Dạ, LogiX thành thật xin lỗi anh/chị vì sự bất tiện này... LogiX đã hoàn 55.000đ cho đơn O-404. Một lần nữa LogiX xin lỗi..."` | `PASS` | `FAIL` | **Người** | **Sai tiền** (`55.000đ` vs ledger `35.000đ`) được bọc trong lời xin lỗi dài, lặp lại (`verbosity/apology bias`). Judge bị đánh lừa bởi giọng xin lỗi nên chấm `PASS`. **Hành động:** loại judge `helpful`; không bao giờ giao kiểm tra tiền bạc cho LLM judge. |
| 13 | `judge_helpful_public.csv` | `HL-047` | `"Ok bạn, đơn O-515 xử lý rồi nhé."` | `PASS` | `FAIL` | **Người** | **Sai xưng hô** (`"Ok bạn"`, `"rồi nhé"`) và thiếu thông tin kết quả cụ thể nhưng judge vẫn cho `PASS`. **Hành động:** xử lý phần xưng hô bằng `tone_ok` (đã cập nhật rubric) và phần kết quả/số tiền bằng code grader. |

## Kết luận

- **Tiêu chí bị loại và lý do (`helpful` — không được dùng làm CI gate):**
  - Dù `Precision = 1.000` và `Specificity = 1.000`, `helpful` **thất bại nặng ở `Recall = 0.300` (< 0.7) và `κ = 0.375` (< 0.6)**.
  - Trên ma trận nhầm lẫn (`tp=9, fp=0, fn=21, tn=70`), judge bỏ sót **21/30 ca lỗi thật (`FN = 21`)**, khiến tỉ lệ lỗi quan sát được chỉ là `0.090` (9%) trong khi tỉ lệ lỗi thực sau hiệu chỉnh Rogan-Gladen là `0.300` (30%).
  - Phân tích toàn bộ `21` ca `FN` trong `judge_helpful_public.csv`:
    - **18/21 ca** là lỗi **sai tiền** (reply nói sai số tiền so với `refund_ledger` — FM-08), gồm **13 ca** bọc số tiền sai trong lời xin lỗi dài dòng lặp lại (`HL-016`, `HL-028`, `HL-035`, `HL-041`, `HL-043`, `HL-053`, `HL-058`, `HL-070`, `HL-072`, `HL-074`, `HL-090`, `HL-096`, `HL-098`) và **5 ca** câu ngắn lịch sự sai tiền (`HL-015`, `HL-020`, `HL-062`, `HL-087`, `HL-100`). Judge hoàn toàn mù trước lỗi này vì không đọc được sổ cái và mắc thiên kiến độ dài/lịch sự (*verbosity & apology bias*).
    - **3/21 ca** còn lại là lỗi **sai xưng hô** (`HL-047`, `HL-091`, `HL-097`).
  - Vi phạm nguyên tắc thiết kế cốt lõi: **tiền và approval luôn chấm bằng code, tuyệt đối không chấm bằng judge**. Nếu đưa `helpful` vào CI gate, hệ thống sẽ lọt toàn bộ lỗi FM-08 (`misreport`) và cho merge các bản sửa đổi trả lời sai số tiền cho khách.
  - Giải pháp thay thế: giữ `tone_ok` cho giọng điệu bề mặt (kèm sửa nhãn `H-081` và cập nhật rubric 6 điểm ở trên), còn toàn bộ kiểm tra tính đúng của số tiền trong reply phải dùng **code grader** (`ReplyMatchesLedger` ở M3) so khớp số tiền trích từ event `reply` với `snapshot["refund_vnd"]`.

- **Rủi ro còn lại:**
  - Cả hai judge chỉ mới được kiểm định trên **dữ liệu replay đã công khai** (`n = 100` mẫu/tiêu chí); chưa đánh giá trên phân phối đầu ra mới từ LLM thật trong môi trường production hoặc các mẫu câu ngoài bộ replay.
  - Tập `judge_tone_public.csv` vẫn còn ít nhất 1 nhãn người sai (`H-081`); cần rà soát lại bộ nhãn và thu thập **tập nhãn người mới (held-out thật)** để tái hiệu chỉnh sau khi sửa rubric trước khi dùng cho quyết định phát hành tự động.
