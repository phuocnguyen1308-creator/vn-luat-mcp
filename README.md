# vn-luat-mcp

MCP server tra cứu **pháp luật Việt Nam** trên PostgreSQL — gộp **Bộ Pháp Điển** (luật thành văn, 64k điều) và **Án lệ / bản án** (toaan.gov.vn). Dùng full-text search tiếng Việt (tìm cả khi gõ không dấu); Claude tự mở rộng từ khóa và xếp hạng để đạt hiệu quả gần ngữ nghĩa.

Chạy được trên **Claude Desktop** và **Claude Code CLI**. Kết nối tới PostgreSQL bằng user **chỉ-đọc** (an toàn).

## Công cụ (tools)

**Luật thành văn:** `tra_luat`, `xem_dieu_luat`, `tra_luat_theo_chu_de`, `liet_ke_chu_de`, `tra_thuat_ngu`
**Án lệ:** `tra_an_le`, `xem_an_le`, `an_le_theo_dieu_luat` (bắc cầu án lệ ↔ điều luật), `tra_cau_an_le`

## Yêu cầu database

PostgreSQL với extension `unaccent`, và các bảng: `articles`, `chapters`, `subjects`, `ontology_topics`, `ontology_glossary` (pháp điển); `anle_documents`, `anle_sentences` (án lệ). Mỗi bảng văn bản có cột `search_vector tsvector` + chỉ mục GIN.

Tạo user chỉ-đọc:

```sql
CREATE USER mcp_ro WITH PASSWORD 'mat_khau_chi_doc';
GRANT CONNECT ON DATABASE appdb TO mcp_ro;
GRANT USAGE ON SCHEMA public TO mcp_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO mcp_ro;
```

## Cấu hình kết nối (biến môi trường)

`PGHOST` (mặc định 127.0.0.1), `PGPORT` (5432), `PGDATABASE` (appdb), `PGUSER` (mcp_ro), `PGPASSWORD`.

## Chạy từ GitHub (không cần cài vào máy)

Cần [`uv`](https://docs.astral.sh/uv/) (`brew install uv`). Lệnh chạy server:

```bash
uvx --from git+https://github.com/USER/vn-luat-mcp vn-luat-mcp
```

`uvx` tự tải và tạo môi trường tạm — không lưu bản sao trong dự án của bạn.

### Claude Desktop

Sửa `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "luat": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/USER/vn-luat-mcp", "vn-luat-mcp"],
      "env": {
        "PGHOST": "100.85.147.69",
        "PGDATABASE": "appdb",
        "PGUSER": "mcp_ro",
        "PGPASSWORD": "mat_khau_chi_doc"
      }
    }
  }
}
```

Khởi động lại Claude Desktop, rồi thử: *"tra luật về an toàn thực phẩm"*.

### Claude Code CLI

Đăng ký nhanh (phạm vi user):

```bash
claude mcp add-json luat '{
  "command": "uvx",
  "args": ["--from", "git+https://github.com/USER/vn-luat-mcp", "vn-luat-mcp"],
  "env": {"PGHOST":"100.85.147.69","PGDATABASE":"appdb","PGUSER":"mcp_ro","PGPASSWORD":"mat_khau_chi_doc"}
}'
```

Hoặc dùng theo dự án: sao chép `.mcp.json.example` thành `.mcp.json` trong thư mục dự án (đã được `.gitignore`).

## Bảo mật

Chỉ kết nối bằng user chỉ-đọc. Nên đặt PostgreSQL sau mạng riêng (vd Tailscale), không mở ra Internet. **Không commit** mật khẩu — dùng `.env` / cấu hình client (đã `.gitignore`).

## License

MIT
