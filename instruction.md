# Classroom AI Summary Bot (v3 Hybrid)

Hướng dẫn này dành cho AI coding agent (Codex/Claude Code) khi làm việc trong repo này. Đọc kỹ trước khi sửa code. Nếu có xung đột giữa comment trong code cũ và file này, **file này là nguồn sự thật**.

---

## 1. Bối cảnh dự án

Bot Discord tóm tắt hoạt động channel lớp học bằng AI, kiến trúc **hybrid 3 tầng**:

- **Ingest**: liên tục, rẻ, không gọi LLM — nhận event qua Discord Gateway WS, ghi vào Redis Stream.
- **Process**: tốn token — chỉ chạy khi có trigger (cron 3 lần/ngày hoặc lệnh on-demand `/summary now`), pipeline Map→Reduce qua AI Service.
- **Deliver**: post milestone công khai **bất biến** (không edit sau khi đăng) + trả lời ephemeral fresh cho ai hỏi giữa mốc, không spam kênh chung.

Mục tiêu thiết kế: không miss dữ liệu (edit/delete Discord), chi phí AI có giới hạn (bounded), trải nghiệm người dùng mượt.

---

## 2. Bất biến (invariant) — KHÔNG ĐƯỢC VI PHẠM

```
if trigger == "cron" && post_success: cursor = last_message_id
if trigger == "on-demand" || trigger == "thread-append": # KHÔNG BAO GIỜ chạm cursor
```

- Chỉ trigger cron mới được cập nhật `cursor`, và chỉ **sau khi** post Discord thành công (trong transaction).
- Mọi trigger khác (on-demand, thread append định kỳ) đọc cursor nhưng tuyệt đối không ghi.
- Post milestone công khai không bao giờ bị edit sau khi đăng — muốn cập nhật thì append vào thread riêng, không sửa post gốc.
- Mọi thay đổi code động vào các đường dẫn xử lý cursor/post đều phải có test kèm theo verify invariant này.

Nếu một task yêu cầu bạn sửa logic có khả năng phá vỡ 2 quy tắc trên, **dừng lại và hỏi lại người dùng** trước khi code tiếp.

---

## 3. Kiến trúc & luồng dữ liệu

```
Discord Gateway WS
   │ MESSAGE_CREATE / UPDATE / DELETE / REACTION_ADD/REMOVE
   ▼
Filter nhanh (bỏ DM, bot msg, tin <3 ký tự, channel chưa opt-in)
   ▼
Redis Stream: stream:{channel_id}       Redis Hash: react:{message_id}
   │
   │  (chỉ đọc khi có trigger)
   ▼
Process pipeline (Map → Reduce)
   1. Đọc tin sau cursor (fallback REST nếu stream bị trim)
   2. Normalize (dedupe theo message_id, giữ bản edit mới nhất, loại bản deleted)
   3. Map: chunk 300–500 tin → model rẻ
   4. Reduce: rolling summary cũ + chunk mới → JSON schema cố định
   ▼
DB: bảng summaries (1 row/lần chạy) + bảng items (topic/FAQ/task/deadline/open_question)
   ▼
Deliver
   - cron  → post embed công khai (bất biến) + tạo thread + update cursor
   - on-demand → reply ephemeral, không update cursor
```

---

## 4. Cấu trúc thư mục đề xuất

Nếu repo chưa có cấu trúc, tạo theo dạng này (điều chỉnh theo ngôn ngữ/framework thực tế của repo — kiểm tra `package.json`/`requirements.txt` trước khi giả định):

```
src/
  gateway/           # kết nối Discord WS, event handlers, filter
  ingest/            # ghi Redis Stream, reaction counter
  process/
    trigger-cron.ts
    trigger-ondemand.ts
    pipeline.ts      # logic Map→Reduce dùng chung cho cả 2 trigger
    normalize.ts
  deliver/
    post-milestone.ts
    reply-ephemeral.ts
    thread-append.ts
  storage/
    cursor.ts        # duy nhất nơi được phép ghi cursor
    summaries.repo.ts
    items.repo.ts
  config/
    channel-config.ts
  jobs/
    scheduler.ts      # cron 9h/14h/21h
tests/
  invariant.test.ts   # test bắt buộc cho quy tắc cursor
  ...
```

---

## 5. Quy ước code bắt buộc

- **Ghi cursor**: chỉ được thực hiện trong `storage/cursor.ts`, qua 1 hàm duy nhất (vd `commitCursor(channelId, messageId)`). Không cho phép update cursor trực tiếp bằng raw query ở nơi khác — dễ vi phạm invariant.
- **Pipeline dùng chung**: `trigger-cron.ts` và `trigger-ondemand.ts` phải gọi cùng `pipeline.ts`, chỉ khác ở việc có gọi `commitCursor` sau cùng hay không. Không copy-paste logic Map→Reduce ra 2 nơi.
- **Idempotency**: mọi lần chạy Process phải idempotent theo `(channel_id, cursor_range)` — nếu chạy lại với cùng input, không tạo dữ liệu trùng trong bảng `summaries`.
- **Không dùng deny-list tên kênh** để loại trừ kênh nhạy cảm (vd match `mod|hr|secret`). Dùng allow-list qua `channel_config` (opt-in tường minh).
- **JSON schema output từ AI Service** phải được validate (vd zod/pydantic) trước khi lưu DB; nếu parse lỗi → retry có giới hạn, không lưu dữ liệu rác.
- **Rate-limit/cache cho on-demand**: cache kết quả theo key `(channel_id, cursor)` với TTL ngắn (3–5 phút) để tránh gọi AI Service trùng lặp khi nhiều user hỏi liên tiếp.
- **Lock khi chạy cron**: dùng lock theo `channel_id` (Redis `SETNX` hoặc advisory lock) để tránh 2 lần chạy job chồng nhau nếu lần trước bị chậm.
- **Lỗi Discord API**: retry có backoff, tôn trọng `retry_after` khi gặp 429. Post thất bại → không gọi `commitCursor`.

---

## 6. Việc cần làm (thực hiện theo thứ tự, mỗi mục nên là 1 commit/PR riêng)

1. Setup hạ tầng: Redis (bật persistence AOF/RDB), DB (bảng `summaries`, `items`, `cursors`, `channel_config`), env/secrets.
2. Gateway layer: kết nối WS, đăng ký intents, filter nhanh, ghi Redis Stream + reaction hash.
3. Xử lý edit/delete: đảm bảo `MESSAGE_UPDATE` ghi đè đúng theo `message_id`, `MESSAGE_DELETE` loại tin khỏi input trước khi vào Process.
4. Cursor module (`storage/cursor.ts`) — điểm duy nhất được ghi cursor, kèm test invariant.
5. Pipeline chung Map→Reduce, JSON schema + validation.
6. Trigger cron: đếm ngưỡng `min_messages`, lock theo channel, gọi pipeline, post + tạo thread + commit cursor trong transaction.
7. Trigger on-demand: slash command, defer ephemeral, cache/rate-limit, gọi pipeline, reply ephemeral — không commit cursor.
8. (Tuỳ chọn) Thread append định kỳ — làm rõ có gọi AI hay chỉ liệt kê tin thô; nếu có gọi AI thì áp cùng quy tắc như on-demand.
9. Guardrail vận hành: dead-letter queue cho job lỗi liên tiếp, hard cap tin/lần và lần/ngày, backfill giới hạn 7 ngày qua queue.
10. Logging & metric: log theo trigger type kèm `channel_id`, `cursor_before/after`, `token_used`.
11. Test suite: idempotency, invariant cursor, lock chống chồng job, fallback REST khi stream bị trim, rolling summary không trôi qua nhiều vòng.

---

## 7. Khi không chắc chắn

- Nếu task đụng đến cursor hoặc post milestone → viết test trước, xin xác nhận nếu logic có vẻ vi phạm invariant ở mục 2.
- Nếu chưa rõ ngôn ngữ/framework của repo, kiểm tra file cấu hình hiện có (`package.json`, `go.mod`, `requirements.txt`...) thay vì giả định.
- Không tự ý đổi mốc giờ cron (9h/14h/21h) hay ngưỡng `min_messages` — đây là tham số nghiệp vụ, cần hỏi lại nếu task yêu cầu thay đổi.
