# Hướng dẫn cài đặt và chạy hệ thống

Tài liệu này hướng dẫn chạy Classroom AI Summary Bot bằng Docker Compose. Stack gồm hai tiến trình Python (`bot`, `scheduler`), PostgreSQL và Redis.

Mọi lệnh trong tài liệu được chạy tại thư mục gốc repository, nơi có file `compose.yml`:

```bash
cd ~/AI/VinAI/C3D/K4-3A-E304-C3D
```

## Quy trình nhanh hằng ngày

Bật hệ thống đã được cài đặt trước đó:

```bash
docker compose up -d
docker compose ps -a
```

Theo dõi log bot và scheduler:

```bash
docker compose logs -f bot scheduler
```

Nhấn `Ctrl+C` để thoát màn hình log. Thao tác này **không tắt container** vì hệ thống đang chạy nền với tùy chọn `-d`.

Tắt hệ thống nhưng giữ database và Redis:

```bash
docker compose down
```

Lần sau bật lại bằng `docker compose up -d`; dữ liệu cũ vẫn còn trong Docker volumes.

## 1. Yêu cầu

Cài đặt:

- Docker Engine 24+ và Docker Compose v2.
- Một Discord application có bot token.
- Một AI endpoint tương thích Chat Completions và hỗ trợ JSON output; cấu hình mặc định dùng DeepSeek.

Kiểm tra Docker:

```bash
docker --version
docker compose version
docker info
```

Nếu `docker info` báo không có quyền truy cập `/var/run/docker.sock`, cấu hình quyền Docker cho tài khoản hiện tại theo hướng dẫn của hệ điều hành rồi đăng xuất/đăng nhập lại. Không nên chạy toàn bộ project bằng `sudo` vì dễ tạo file sai owner.

## 2. Tạo Discord bot

Trong Discord Developer Portal:

1. Tạo application và thêm bot.
2. Sao chép bot token để dùng cho `DISCORD_TOKEN`.
3. Bật privileged intent **Message Content Intent**.
4. Mời bot vào test server với các quyền: View Channels, Read Message History, Send Messages, Create Public Threads, Send Messages in Threads và Use Application Commands.

Chỉ thử trên server/channel test trước. Bot không đọc channel cho đến khi quản trị viên opt-in bằng slash command.

## 3. Cấu hình môi trường

Từ thư mục gốc repository:

```bash
cp .env.example .env
```

Mở `.env` và điền các giá trị:

```dotenv
DISCORD_TOKEN=<discord-bot-token>
DATABASE_URL=postgresql+asyncpg://classroom:classroom@postgres:5432/classroom
REDIS_URL=redis://redis:6379/0
AI_BASE_URL=https://api.deepseek.com
AI_API_KEY=<ai-api-key>
AI_MODEL=deepseek-flash
TIMEZONE=Asia/Bangkok
STREAM_MAXLEN=100000
PROCESS_MESSAGE_CAP=2000
ONDEMAND_CACHE_TTL_SECONDS=240
ONDEMAND_RATE_LIMIT_SECONDS=30
CRON_LOCK_TTL_SECONDS=1800
LOG_LEVEL=INFO
```

Không commit `.env`. Các hostname `postgres` và `redis` là tên service nội bộ trong Compose; không đổi thành `localhost` khi bot chạy trong container.

Ví dụ khi dùng DeepSeek:

```dotenv
AI_BASE_URL=https://api.deepseek.com
AI_API_KEY=<deepseek-api-key>
AI_MODEL=deepseek-flash
```

Adapter dùng JSON mode của Chat Completions và tiếp tục validate kết quả bằng Pydantic trước khi lưu.

## 4. Build và khởi động lần đầu

Khởi động toàn bộ stack:

```bash
docker compose up --build -d
```

Trong lệnh trên:

- `--build` tạo lại image ứng dụng từ source code.
- `-d` chạy container dưới nền để terminal tiếp tục sử dụng được.

Compose sẽ thực hiện theo thứ tự:

1. Khởi động PostgreSQL và Redis.
2. Chạy `alembic upgrade head` trong service `migrate`.
3. Khởi động Discord Gateway bot và scheduler.

Kiểm tra trạng thái và log:

```bash
docker compose ps -a
docker compose logs migrate
docker compose logs -f bot scheduler
```

Service `migrate` phải kết thúc với `Exited (0)`; đây là trạng thái bình thường của job migration chạy một lần. `postgres`, `redis`, `bot` và `scheduler` phải ở trạng thái `healthy` sau khoảng 30–60 giây.

Nếu chỉ thấy `Started`, chờ rồi kiểm tra lại:

```bash
docker compose ps -a
```

Chạy health check thủ công:

```bash
docker compose exec bot classroom-healthcheck
```

Lệnh không in lỗi và trả exit code `0` nghĩa là PostgreSQL, Redis, Discord và AI provider đều kết nối được.

## 5. Quản lý container và theo dõi log

### Bật, tắt và restart

```bash
# Bật các container đã có, không build lại image
docker compose up -d

# Dừng tạm thời nhưng giữ container
docker compose stop

# Chạy lại các container đã stop
docker compose start

# Restart nhanh toàn bộ service
docker compose restart

# Restart riêng bot
docker compose restart bot

# Tắt và xóa container/network, vẫn giữ dữ liệu volumes
docker compose down
```

`docker compose restart` không nạp source code hoặc `.env` mới. Hãy dùng `up --build --force-recreate` sau khi sửa code, hoặc `up --force-recreate` sau khi sửa `.env` như bên dưới.

Sau khi sửa source code, phải build lại vì code được đóng gói trong image:

```bash
docker compose up --build -d --force-recreate bot scheduler
```

Sau khi chỉ sửa `.env`, không cần build image:

```bash
docker compose up -d --force-recreate bot scheduler
```

### Đọc và thoát log

```bash
# Theo dõi liên tục tất cả log
docker compose logs -f

# Chỉ theo dõi bot và scheduler
docker compose logs -f bot scheduler

# Xem 100 dòng gần nhất rồi trả terminal
docker compose logs --tail=100 bot

# Xem log phát sinh trong 10 phút gần nhất
docker compose logs --since=10m bot

# Xem log migration
docker compose logs migrate
```

Với lệnh có `-f`, nhấn `Ctrl+C` để ngừng theo dõi. Không dùng `docker compose down` chỉ để thoát log.

### Hiểu trạng thái

- `healthy`: service đang chạy và health check thành công.
- `unhealthy`: service vẫn có thể đang chạy nhưng health check lỗi; xem log và chạy `classroom-healthcheck`.
- `Exited (0)` của `migrate`: migration thành công.
- `Exited (1)` hoặc `Restarting`: tiến trình lỗi; xem `docker compose logs <service>`.

## 6. Kiểm tra database và Redis

Liệt kê bảng PostgreSQL:

```bash
docker compose exec postgres psql -U classroom -d classroom -c '\dt'
```

Kiểm tra migration và cursor:

```bash
docker compose exec postgres psql -U classroom -d classroom -c 'select * from alembic_version;'
docker compose exec postgres psql -U classroom -d classroom -c 'select * from cursors;'
```

Kiểm tra Redis:

```bash
docker compose exec redis redis-cli ping
docker compose exec redis redis-cli scan 0 match 'stream:*'
```

PostgreSQL và Redis dùng named volumes nên dữ liệu vẫn tồn tại sau `docker compose down`.

## 7. Bật bot trong Discord

Trong channel test, tài khoản có quyền Manage Channels chạy:

```text
/summary enable min_messages:5
```

Sau đó gửi ít nhất 5 tin nhắn hợp lệ. Kiểm tra nhanh bằng:

```text
/summary now
```

Kết quả on-demand chỉ hiện ephemeral và không cập nhật cursor. Scheduler đăng milestone công khai lúc 09:00, 14:00 và 21:00 theo `TIMEZONE`; chỉ sau khi post thành công cron mới cập nhật cursor.

Tin nhắn hợp lệ phải được gửi **sau khi enable**, do người dùng thật gửi và có ít nhất 3 ký tự. Tin nhắn của bot, DM và nội dung quá ngắn bị bỏ qua.

Theo dõi lần chạy on-demand:

```bash
docker compose logs -f bot
```

Sau khi thấy kết quả hoặc lỗi, nhấn `Ctrl+C` để trở lại terminal.

Kiểm tra dữ liệu summary:

```bash
docker compose exec postgres psql -U classroom -d classroom -c \
  'select channel_id, trigger, status, token_usage, model from summaries;'
```

On-demand không được ghi cursor. Cursor chỉ xuất hiện sau khi cron post công khai thành công:

```bash
docker compose exec postgres psql -U classroom -d classroom -c \
  'select * from cursors;'
```

Tắt channel bằng:

```text
/summary disable
```

## 8. Migration, test và cập nhật phiên bản

Chạy migration thủ công:

```bash
docker compose run --rm migrate
```

Chạy bộ kiểm tra ngoài Docker bằng Python 3.11+:

```bash
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
mypy src
pytest -q
```

Sau khi pull code mới:

```bash
docker compose build
docker compose run --rm migrate
docker compose up -d
```

## 9. Backup, reset và xử lý lỗi

Backup PostgreSQL:

```bash
docker compose exec -T postgres pg_dump -U classroom classroom > classroom-backup.sql
```

Khôi phục vào database đang chạy từ file backup:

```bash
docker compose exec -T postgres psql -U classroom -d classroom < classroom-backup.sql
```

Chỉ restore vào database phù hợp và nên tạo thêm một bản backup mới trước khi ghi đè dữ liệu.

Các kiểm tra thường dùng:

- Không thấy slash command: kiểm tra bot đã được mời với scope `applications.commands`, rồi xem `bot` logs.
- Bot không ingest: kiểm tra Message Content Intent và channel đã chạy `/summary enable`.
- AI trả lỗi 400: kiểm tra `AI_BASE_URL`, tên model và khả năng hỗ trợ JSON output.
- DeepSeek trả 401: kiểm tra `AI_BASE_URL=https://api.deepseek.com` và API key trong `.env`.
- DeepSeek trả 402: tài khoản không đủ số dư API.
- `/summary now` báo lỗi chung: chạy `docker compose logs --since=10m bot` để lấy traceback thật.
- Discord 403: kiểm tra quyền đọc, gửi message và tạo public thread trong channel.
- Cron không post: kiểm tra `min_messages`, timezone, Redis lock và log `scheduler`.
- Post lỗi thì cursor phải giữ nguyên; kiểm tra bảng `cursors` trước khi chạy lại.

Lệnh `docker compose down -v` xóa toàn bộ volume PostgreSQL và Redis, không thể khôi phục nếu chưa backup. Chỉ dùng khi chủ động muốn reset sạch môi trường development.

Quy trình reset sạch:

```bash
docker compose down -v
docker compose up --build -d
```

Sau reset, migration tự chạy lại nhưng toàn bộ channel config, summaries và cursors cũ đã bị xóa.

## 10. Checklist hoàn tất

- [ ] `docker compose ps -a` hiển thị PostgreSQL, Redis, bot và scheduler là `healthy`.
- [ ] Migration hiển thị `Exited (0)`.
- [ ] `docker compose exec bot classroom-healthcheck` chạy không có traceback.
- [ ] Bot xuất hiện online trong Discord.
- [ ] Channel đã chạy `/summary enable`.
- [ ] `/summary now` trả kết quả ephemeral.
- [ ] Bảng `summaries` có dữ liệu và on-demand không thay đổi bảng `cursors`.
- [ ] Đã biết dùng `Ctrl+C` để thoát log và `docker compose down` để tắt hệ thống.
