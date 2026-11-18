# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

## Phân tích ca lỗi (`seeded_regression C-002@11`)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11` (trial `R-seeded_regression-C-002-s11`, report `E-seeded_regression-20261118-6390` trong `src/reports/eval_seeded_regression.json`) |
| Triệu chứng | `TrialPass` (`pass_rate`) **FAIL** (`status resolved != denied`); `RefundAmountCorrect` (`refund_amount_correct`) **FAIL** (`ledger=20000 != expected=0`); `DbFactKept` (`db_fact_kept`) **FAIL** (`1 override event(s)`). Reply nói `"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."` — khớp số `20000` mà ledger đã ghi nhầm, trong khi nhãn yêu cầu từ chối (`status=denied`, `refund_vnd=0`, `refund_count=0`). |
| Bước sai đầu tiên | **Event #3 `model_override`**: `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | **Event #1 `handoff`** khởi tạo `REQ-C-002` đúng scope `owner_order_only` và `allowed_tools` chuẩn. **Event #2 `investigator`** (`lookup_order`) đọc đúng dữ liệu đơn `O-202` từ SQLite (`visible: true`, `status: "delivered"`, `delay_days: 2` — nhỏ hơn ngưỡng 3 ngày của `SHIP-LATE-03`). Chỉ tới **Event #3 `model_override`**, agent mới dùng số ngày `5` parse từ ticket khách để ghi đè `delay_days` của DB, kéo theo **Event #4 `quote`** tính sai thành `20000` và kích hoạt hoàn tiền nhầm. |
| Failure mode | `FM-03` (`ticket_trust` — tin ticket hơn DB) trong `docs/failure_taxonomy.md` |
| Đối chứng | Cùng `C-002@11` trên shape `fixed` (`E-fixed-20261118-6390`): sau Event #1 `handoff` và Event #2 `investigator` (`delay_days: 2`), **không có event `model_override`**. **Event #3 `quote`** trả `{"amount_vnd": 0, "reason": "no_entitlement", "clause_ids": [], "parts": {}}`, **Event #4 `reply`** từ chối đúng (`"Dạ, đơn O-202 chưa đủ điều kiện hoàn theo chính sách hiện hành."`), ledger `0đ`, `status=denied` → **PASS** toàn bộ grader. |
| Regression test | `tests/test_lab9_trace_case.py::test_c002_ticket_override_regression` (gọi `lab9.trace_case.investigate`, assert `DbFactKept` và `RefundAmountCorrect` **FAIL** trên `seeded_regression C-002@11` với `ledger=20000 != expected=0`, và **PASS** trên `fixed C-002@11`); chạy được bằng `pytest -q -m student -o addopts= -k "lab9 and not advanced"`. Đồng thời item `E-002` (`C-002`) trong `data/eval/eval_set_v1.jsonl` đã gắn `failure_modes: ["FM-03"]` (và bổ sung thêm ca tấn công `C-101`, `C-102` ở v2). |
| Chưa chắc chắn | Trace chạy trên `MockLLM` với parser `parse_delay_days` cố định, nên chưa đo được tỉ lệ LLM thật tự trích xuất sai hoặc bị lừa bởi prompt injection đa dạng hơn (như `C-101`). Ngoài ra `DbFactKept` chỉ bắt được lỗi nếu biến thể ghi lại event `model_override`; nếu agent âm thầm ghi đè không log event (như biến thể ẩn `quiet_override`), chỉ có thể phát hiện ở tầng outcome qua `RefundAmountCorrect` và `TrialPass`. |

## Quy tắc đã tuân thủ

- Đã đối chiếu **ledger trước reply**: trên `C-002@11`, reply trôi chảy (`20.000đ`) vẫn đi kèm một khoản hoàn sai so với nhãn (`0đ`).
- Bước sai đầu tiên dẫn đúng số event 1-based (`Event #3 model_override`) từ output thực của `lab9.trace_case`.
- Đã có regression test chạy tự động trong `src/tests/test_lab9_trace_case.py` và bổ sung test đối chứng thêm cho `C-007@11` (`FM-08` `ReplyMatchesLedger`).
