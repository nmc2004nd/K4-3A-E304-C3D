# AI SPEC — Classroom AI Summary Bot · Nhóm C3D · Zone 2

**Hướng:** B — Trợ lý Học viên (Discord Bot)  
**Loại:** Tính năng mới  
**Mức prototype:** Working MVP  
**Quality bar chốt:** 21:00 ngày 17/09/2026

Tài liệu này tổng hợp [Canvas CP1](../CP1/Canva1.jpg), [luồng trải nghiệm CP2](../CP2/classroom-summary-interaction-flow.html), [kiến trúc CP3](../CP3/pipeline.html) và trạng thái code tại thời điểm chốt CP4. Nội dung chưa có bằng chứng được ghi rõ, không suy đoán số liệu.

## §1. User & Job

### Người dùng và công việc cần hoàn thành

- **Người dùng chính:** học viên đã sử dụng bot Trợ lý Kute trong các channel lớp học.
- **Job executor:** học viên quay lại Discord sau khi bỏ lỡ một khoảng hội thoại; admin cấu hình channel được phép tổng hợp.
- **Core JTBD:** Khi quay lại một channel sau một khoảng vắng mặt, học viên muốn nắm nhanh nội dung quan trọng, việc cần làm, deadline và câu hỏi còn mở để quyết định cần đọc hoặc hành động tiếp ở đâu.
- **Problem statement:** Nội dung quan trọng bị trôi trong chuỗi hội thoại dài; người học phải đọc lại nhiều tin, dễ bỏ sót hướng dẫn và deadline.

Workflow hiện tại: admin opt-in channel một lần bằng `/summary enable` → bot thu thập tin mới → học viên dùng `/summary now` khi cần, hoặc scheduler đăng mốc công khai lúc 09:00, 14:00 và 21:00 nếu đủ ngưỡng.

### Bằng chứng hiện có

CP1 ghi nhận nguồn là “phiếu khảo sát từ người dùng thực tế”, mức tin cậy “Cao — đã xác thực”, và nỗi đau là nhu cầu tóm tắt nội dung nổi bật trong ngày. Tuy nhiên repo **chưa lưu bản export khảo sát**, chưa có `n`, tỷ lệ xác nhận hay link đầy đủ có thể kiểm chứng từ ảnh.

| Bằng chứng | Trạng thái | Việc phải bổ sung |
|---|---|---|
| Canvas vấn đề/giải pháp | Có tại CP1 | Giữ làm bằng chứng định hướng |
| Cỡ mẫu và tỷ lệ xác nhận | Chưa có trong repo | Ghi `n`, câu hỏi khảo sát, số người chọn và tỷ lệ |
| ≥5 quote nguyên văn | Chưa có trong repo | Thêm quote ngắn, mã người dùng ẩn danh và nguồn |
| Log/phụ lục khảo sát | Chưa có | Lưu bản đã ẩn danh; không commit dữ liệu nhạy cảm |

Không được dùng nội dung hội thoại demo do nhóm tự nhập làm bằng chứng nhu cầu người dùng.

## §2. Impact & quyết định chọn

Điểm dưới đây là **đánh giá nội bộ 1–5**, chưa thay thế số liệu khảo sát. `Tổng = Reach + Frequency + Pain + Feasibility`.

| Ứng viên | Reach | Frequency | Pain | Feasibility | Tổng | Quyết định |
|---|---:|---:|---:|---:|---:|---|
| Tóm tắt channel theo lịch và khi được hỏi | 4 | 5 | 4 | 5 | **18** | Chọn |
| Gom câu hỏi trùng thành FAQ | 3 | 4 | 3 | 4 | 14 | Là một loại item trong summary, không tách sản phẩm |
| Cảnh báo riêng cho coach khi có câu chưa giải quyết | 2 | 3 | 5 | 3 | 13 | Hoãn; cần xác định người nhận và tránh spam |

Giải pháp được chọn vì giải đúng nỗi đau CP1, phục vụ cả nhu cầu chủ động và tự động của CP2, đồng thời đã có working MVP. Trước CP5, nhóm phải thay Reach/Frequency giả định bằng số người và tần suất thực từ khảo sát.

## §3. Giải pháp tương tự đã nghiên cứu

| Giải pháp | Đáng học | Hạn chế cần tránh | Khác biệt của nhóm |
|---|---|---|---|
| Discord Search | Truy xuất lại tin gốc, có ngữ cảnh channel | Người dùng vẫn phải tự đọc và tổng hợp | Bot tạo overview có cấu trúc: topic, FAQ, task, deadline, open question |
| Bản tin/pinned message thủ công | Nội dung được con người kiểm soát | Tốn công, chậm và không đáp ứng khi hỏi giữa hai mốc | Hybrid: mốc công khai cố định và bản fresh ephemeral theo yêu cầu |

Repo chưa có log benchmark sản phẩm ngoài. Nếu dùng tên/screenshot sản phẩm cụ thể trong pitch, nhóm phải bổ sung nguồn và ngày truy cập.

## §4. Thiết kế

### Lát cắt

**Một học viên quay lại channel đã được admin bật Summary, yêu cầu xem phần hội thoại mới, hệ thống chọn và cấu trúc thông tin có căn cứ thành bản tóm tắt tiếng Việt riêng tư để học viên biết việc cần làm tiếp theo.**

### Phạm vi và mức tự động hóa

- **Working thật:** Discord Gateway, Redis Stream, PostgreSQL, DeepSeek-compatible API, `/summary enable`, `/summary now`, `/summary disable`, Map→Reduce, JSON validation, scheduler, Docker Compose và healthcheck.
- **Conditional automation:** scheduler chỉ xử lý channel opt-in và chỉ đăng khi đủ `min_messages`; on-demand chỉ chạy khi có tin mới.
- **Augment:** AI rút gọn và phân loại; người dùng vẫn đọc nguồn trong channel và tự quyết định hành động.
- **Automate có rào chắn:** cron đăng milestone tự động, nhưng chỉ cập nhật cursor sau khi Discord post thành công.

### Invariant bắt buộc

```text
cron + post thành công  → cập nhật cursor tới tin cuối đã xử lý
on-demand              → không bao giờ cập nhật cursor
post milestone         → không sửa sau khi đã đăng
```

### Non-goals của MVP

1. Không đọc mọi channel mặc định; chỉ dùng allow-list do admin opt-in.
2. Không trả lời thay coach hoặc tự tạo quy định lớp học.
3. Không sửa post milestone đã công bố.
4. Không backfill không giới hạn; fallback REST tối đa bảy ngày và có hard cap.
5. Chưa làm thread append định kỳ, nút feedback/tạo task hoặc dashboard quản trị.

### Nguyên tắc HAX/PAIR đã áp dụng

| Nguyên tắc | Áp dụng trong prototype |
|---|---|
| Nêu rõ khả năng và giới hạn | Slash command tách enable/now/disable; channel chưa bật và không có tin mới có thông báo riêng |
| Hỗ trợ gọi đúng lúc | Có lịch cố định và `/summary now` giữa các mốc |
| Giảm tác động khi AI sai | Output phải qua Pydantic schema; parse sai retry tối đa ba lần, không lưu JSON rác |
| Trao quyền kiểm soát | Admin chủ động opt-in/disable và chọn `min_messages`; on-demand trả ephemeral |
| Học từ sửa đổi của người dùng | Normalize giữ bản edit mới nhất và loại tin đã xóa trước khi xử lý |
| Giữ hành vi nhất quán | Cron và on-demand dùng chung Map→Reduce; prompt bắt buộc phần diễn giải bằng tiếng Việt |

## §5. Kiểu lỗi và kịch bản rủi ro

| Lớp | Kịch bản | Hành vi mong đợi / điều kiện đạt |
|---|---|---|
| Dữ liệu vào | Tin bị edit sau khi ingest | Chỉ nội dung mới nhất xuất hiện trong input |
| Dữ liệu vào | Tin bị xóa | Không xuất hiện trong summary |
| Dữ liệu vào | Có DM, bot message hoặc tin dưới 3 ký tự | Bị loại trước khi ghi stream |
| Dữ liệu vào | Redis Stream đã trim mất mốc cursor | Fallback Discord REST, không bỏ qua tin hợp lệ |
| Mô hình | AI trả JSON sai schema | Retry có giới hạn; vẫn sai thì báo lỗi và không lưu dữ liệu rác |
| Mô hình | AI bịa fact/deadline hoặc trộn hội thoại cá nhân | Case fail; mọi item phải được đối chiếu với source message ID |
| Mô hình | AI trả nội dung tiếng Anh | Case fail, trừ tên riêng/thuật ngữ/code cần giữ nguyên |
| Tương tác | Channel chưa enable hoặc chưa có tin mới | Trả thông báo rõ ràng, không gọi AI khi không cần |
| Tương tác | Nhiều người gọi `/summary now` liên tiếp | Rate-limit theo user; cache 3–5 phút theo channel/cursor/prompt version |
| Hệ thống | Hai cron chạy chồng nhau | Redis lock cho phép tối đa một job/channel |
| Hệ thống | Discord post lỗi/429 | Retry theo `retry_after`; post thất bại tuyệt đối không cập nhật cursor |
| Riêng tư | Dữ liệu channel A xuất hiện ở summary channel B | Hard fail toàn bộ release; dữ liệu phải cô lập theo `channel_id` |

## §6. Bốn đường đi của trải nghiệm

### 1. Happy path

Admin chạy `/summary enable min_messages:5` một lần. Sau khi có tin mới, học viên chạy `/summary now`, bot defer interaction, tạo summary tiếng Việt và trả ephemeral. Đến mốc cron, nếu đủ ngưỡng, bot đăng embed công khai, tạo thread và mới cập nhật cursor.

### 2. Low-confidence

Schema có `open_question` để giữ nội dung chưa đủ căn cứ thay vì biến thành kết luận. MVP hiện **chưa có confidence score**; do đó case mơ hồ chỉ đạt khi được ghi là câu hỏi mở hoặc bị bỏ qua, không được khẳng định thành fact.

### 3. Failure / không có căn cứ

Không có tin mới → “Chưa có tin nhắn mới để tổng hợp”. Channel chưa opt-in → “Channel chưa được bật Summary”. AI/DB lỗi → thông báo thất bại chung cho user và traceback trong log; không thay đổi cursor.

### 4. Correction

Người dùng sửa hoặc xóa tin gốc trước lần xử lý kế tiếp; normalize dùng phiên bản mới nhất. Milestone công khai đã đăng là bất biến: MVP không sửa post cũ. Thread correction/append là hướng mở rộng, chưa triển khai.

### Ngoài phạm vi và case domain

- Yêu cầu tổng hợp channel chưa opt-in bị từ chối, không tự động mở quyền.
- Hội thoại học tập lẫn chuyện cá nhân: target là bỏ phần không phục vụ topic/FAQ/task/deadline/open question; bộ test phải có case hỗn hợp.
- Deadline tương đối như “chiều mai” chỉ đạt khi không tự suy diễn ngày tuyệt đối nếu thiếu timezone/ngày gốc.

## §7. Kiểm thử và quality bar

### 7.1 Kiểm thử tự động hiện có

Chạy tại thư mục gốc:

```bash
python -m pip install -e '.[dev]'
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m pytest -q
```

Tại thời điểm chốt, `pytest` có **16/16 test pass**. Các test bao phủ:

- edit/delete normalization;
- chỉ một nơi được ghi cursor;
- on-demand không ghi cursor;
- Discord post lỗi không ghi cursor, post thành công mới ghi;
- cron lock chống chạy chồng;
- idempotency theo channel và cursor range;
- fallback REST khi stream bị trim;
- JSON schema retry có giới hạn và DeepSeek JSON mode;
- liên kết `items.summary_id` và prompt đầu ra tiếng Việt.

### 7.2 Smoke test Docker

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps -a
docker compose exec bot classroom-healthcheck
docker compose logs --since=10m bot scheduler
```

Đạt khi PostgreSQL, Redis, bot và scheduler đều `healthy`; migration `Exited (0)`; healthcheck exit code 0; log không có traceback lặp lại. Nhóm đã chạy được stack và gọi DeepSeek/Discord thành công, nhưng log/video minh chứng CP3 **chưa được lưu trong repo**.

### 7.3 Acceptance test trên Discord

1. Admin chạy `/summary enable min_messages:3` trong channel test.
2. Gửi ít nhất ba tin hợp lệ, gồm một topic, một task và một deadline; thêm một tin cá nhân để kiểm tra lọc nhiễu.
3. Chạy `/summary now`: kết quả phải ephemeral, tiếng Việt, không bịa và không đổi bảng `cursors`.
4. Sửa một tin, xóa một tin rồi gọi lại sau khi cache hết hạn: chỉ bản mới nhất còn xuất hiện.
5. Tại mốc cron kế tiếp, milestone chỉ được đăng khi đủ ngưỡng; sau khi post thành công cursor bằng ID tin cuối đã xử lý.
6. Kiểm tra DB:

```bash
docker compose exec postgres psql -U classroom -d classroom \
  -c 'select channel_id, last_message_id from cursors;'
docker compose exec postgres psql -U classroom -d classroom \
  -c 'select trigger, status, cursor_from, cursor_to, token_usage from summaries order by created_at desc;'
```

### 7.4 Golden set phải hoàn thành

Tạo `eval/golden-set.jsonl` gồm **24 case đã gắn expected output/rubric**:

| Nhóm case | Số lượng |
|---|---:|
| Topic/FAQ học tập rõ ràng | 6 |
| Task và deadline, gồm thời gian tương đối | 4 |
| Nội dung học tập trộn trò chuyện cá nhân | 4 |
| Edit, delete, duplicate và reaction | 4 |
| Không có dữ liệu/ngoài phạm vi/JSON lỗi | 3 |
| Cursor, post failure, concurrency và cô lập channel | 3 |
| **Tổng** | **24** |

Repo hiện **chưa có thư mục `eval/`**, vì vậy chưa được tuyên bố đã hoàn thành golden-set evaluation.

### 7.5 Định nghĩa một case nội dung “đạt”

Một case chỉ pass khi đồng thời:

1. JSON hợp lệ theo schema và hiển thị được trên Discord.
2. `overview`, `title`, `detail` bằng tiếng Việt; cho phép giữ thuật ngữ/tên riêng/code.
3. Không có fact, task hoặc deadline không được hỗ trợ bởi input.
4. 100% task/deadline trọng yếu trong expected set được giữ đúng chủ thể và thời gian.
5. Bao phủ ít nhất 80% ý chính đã gắn nhãn cho case.
6. Không đưa nội dung cá nhân đã gắn nhãn `off_topic` vào summary.

### Quality bar đã khóa

> **Sản phẩm đạt khi ít nhất 21/24 case (87,5%) pass; đồng thời 100% case hard-gate về không bịa fact/deadline, cô lập channel, post thất bại không nhảy cursor và on-demand không ghi cursor phải pass. Toàn bộ unit test, Ruff và mypy phải xanh.**

Không được hạ quality bar sau hạn CP4. Nếu kết quả thấp hơn, nhóm báo đúng số thực, phân tích lỗi và tiếp tục cải thiện.

### Kết quả các lượt chạy

| Thời điểm | Bộ test | Kết quả | Ghi chú |
|---|---|---:|---|
| 17/09/2026 | Automated unit tests | 16/16 (100%) | Không phải golden set chất lượng nội dung |
| Chưa chạy | Golden set 24 case | Chưa có số liệu | Bắt buộc bổ sung trước CP5 |
| Chưa chạy | 5 willing users | Chưa có số liệu | Thuộc validation/R6 |

## §8. Phân công và kế hoạch

Phân công dưới đây chi tiết hóa nội dung CP1 (“Đạt, Đoan: dữ liệu/feedback/improve; Cường, Đức: create feature”). Nhóm cần xác nhận lại trước khi nộp.

| Thành viên | Trách nhiệm chính | Bằng chứng đầu ra |
|---|---|---|
| Hoàng Thái Đạt | Khảo sát, golden set, chấm kết quả | Export khảo sát ẩn danh, `eval/` |
| Đỗ Mạnh Đoan | Spec, evidence, validation log | `CP4/spec.md`, quote và `validation/` |
| Nguyễn Mạnh Cường | Backend, Docker/DB, prompt và test | `src/`, `compose.yml`, test report |
| Vi Hoàng Đức | Discord flow, demo và kiểm thử end-to-end | CP2, video CP3/CP5, checklist demo |

### Việc còn thiếu trước CP5/CP6

- [ ] Bổ sung `n`, tỷ lệ khảo sát và ít nhất 5 quote có nguồn ẩn danh.
- [ ] Khai tên ít nhất 2 willing users đã đăng ký từ CP1; mục này chưa có trong repo.
- [ ] Lưu video CP3 30 giây và số đo thật.
- [ ] Tạo/chấm đủ 24 case trong `eval/`, không chỉ chạy unit test.
- [ ] Cho 5 người ngoài nhóm làm task, ghi quote/kẹt ở đâu/quyết định vào `validation/`.
- [ ] Bổ sung ít nhất một thay đổi dựa trên validation vào changelog.
- [ ] Điền vai trò trong bảng thành viên `README.md` và bảo đảm mọi người giải thích được phần mình làm.

## §9. Changelog

| Thời điểm | Thay đổi | Lý do / bằng chứng |
|---|---|---|
| 16/09/2026 | Chốt vấn đề và lát cắt ban đầu | Canvas CP1 |
| 16/09/2026 | Thiết kế luồng chủ động + theo lịch | Sơ đồ CP2 |
| 17/09/2026 | Chọn kiến trúc hybrid Ingest–Process–Deliver | Pipeline CP3; kiểm soát chi phí và tránh miss dữ liệu |
| 17/09/2026 | Hoàn thành working MVP Docker/Discord/DeepSeek/PostgreSQL/Redis | Code và automated tests trong repo |
| 17/09/2026 | Sửa lỗi liên kết `items.summary_id` | Lỗi integration khi lưu kết quả thật |
| 17/09/2026 | Bắt buộc đầu ra diễn giải bằng tiếng Việt và version hóa prompt/cache | Kết quả demo từng trả tiếng Anh |
| 17/09/2026 | Chốt quality bar 21/24 cùng các hard gate | CP4 — giữ nguyên chuẩn sau thời điểm nộp |
