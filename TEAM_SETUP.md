# Hướng dẫn cho thành viên nhóm (dùng MCP tra cứu pháp luật)

MCP này cho phép Claude tra cứu **Bộ Pháp Điển + Án lệ Việt Nam** ngay trong hội thoại.
Dữ liệu nằm trên một máy chủ PostgreSQL riêng, truy cập an toàn qua **Tailscale** bằng
tài khoản **chỉ-đọc** (bạn không thể sửa/xóa gì).

Người quản trị sẽ gửi cho bạn **3 thứ**: mật khẩu `mcp_ro`, và xác nhận đã *chia sẻ máy Pi*
cho email Tailscale của bạn. Repo này là link GitHub công khai.

## 1. Cài Tailscale & chấp nhận lời mời

- Tải Tailscale: https://tailscale.com/download — cài, đăng nhập bằng email của bạn.
- Mở link mời "shared machine" người quản trị gửi (hoặc kiểm tra trong app Tailscale) và
  **chấp nhận** để thấy được máy chủ (`phuocn`, địa chỉ `100.85.147.69`).
- Kiểm tra thông mạng (Terminal): `ping 100.85.147.69` — có phản hồi là được.

## 2. Cài uv

- **macOS:** `brew install uv`
- **Windows (PowerShell):** `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` — hoặc `winget install astral-sh.uv`
- **Linux:** `curl -LsSf https://astral.sh/uv/install.sh | sh`

Cài xong, **mở lại** Terminal/PowerShell để `uvx` vào PATH.

## 3. Đăng ký MCP vào client

Thay `USER` bằng chủ repo, và `MAT_KHAU_MCP_RO` bằng mật khẩu người quản trị gửi.

### Claude Desktop
Thêm vào file cấu hình (mục `mcpServers`) — vị trí file tùy hệ điều hành:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
"luat": {
  "command": "uvx",
  "args": ["--from", "git+https://github.com/USER/vn-luat-mcp", "vn-luat-mcp"],
  "env": {
    "PGHOST": "100.85.147.69",
    "PGDATABASE": "appdb",
    "PGUSER": "mcp_ro",
    "PGPASSWORD": "MAT_KHAU_MCP_RO"
  }
}
```
Khởi động lại Claude Desktop.

### Claude Code CLI
```bash
claude mcp add-json luat '{"command":"uvx","args":["--from","git+https://github.com/USER/vn-luat-mcp","vn-luat-mcp"],"env":{"PGHOST":"100.85.147.69","PGDATABASE":"appdb","PGUSER":"mcp_ro","PGPASSWORD":"MAT_KHAU_MCP_RO"}}'
```

## 4. Thử

Hỏi Claude: *"tra luật về an toàn thực phẩm"* hoặc *"tìm án lệ về tranh chấp đất đai"*.

## Trục trặc thường gặp

- **`ping` không phản hồi** → chưa chấp nhận chia sẻ máy, hoặc Tailscale chưa bật (Connected).
- **MCP lỗi xác thực** → sai `PGPASSWORD`, hoặc người quản trị chưa tạo tài khoản cho bạn.
- **Kết nối bị chặn** → nhờ quản trị kiểm tra Tailscale ACL cho phép truy cập cổng 5432 của Pi.
- **`uvx` không thấy** → chưa cài `uv` (bước 2), hoặc mở lại Terminal sau khi cài.
