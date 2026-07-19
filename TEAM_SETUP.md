# Hướng dẫn cài đặt cho thành viên nhóm

MCP này cho phép Claude tra cứu **pháp luật Việt Nam** ngay trong hội thoại: Bộ Pháp Điển,
án lệ chính thức, và văn bản gốc từ Công báo Chính phủ.

Dữ liệu nằm trên máy chủ riêng, bạn truy cập qua **Tailscale** bằng tài khoản **chỉ-đọc** —
không thể sửa hay xoá gì.

**Kho dữ liệu hiện có:**

| Nhóm | Số lượng |
|---|---:|
| Điều luật (Bộ Pháp Điển, 43 chủ đề) | 66.031 |
| Án lệ chính thức (toàn văn) | 90 |
| Bản án minh họa | 1.963 |
| Văn bản gốc (Công báo) | 3.268 |

Người quản trị sẽ gửi bạn **3 thứ**: (1) **tên tài khoản riêng của bạn** (dạng `luat_ro_<tên>`),
(2) **mật khẩu** của tài khoản đó, (3) lời mời Tailscale chia sẻ máy chủ. Link repo này là công khai.

> Mỗi thành viên có **tài khoản riêng**, không dùng chung. Nhờ vậy quản trị thu hồi được từng
> người mà không ảnh hưởng ai khác. **Đừng chia sẻ tài khoản của bạn cho người khác** — nếu
> có người mới, báo quản trị cấp tài khoản mới.

---

## 1. Cài Tailscale

1. Tải và cài: https://tailscale.com/download — chọn bản **Windows**.
2. Đăng nhập bằng **đúng email mà người quản trị đã mời**.
3. Mở lời mời "shared machine" trong app hoặc trong email, bấm **Accept**.
4. Kiểm tra thông mạng — mở **PowerShell** và chạy:

   ```powershell
   ping 100.85.147.69
   ```

   Có `Reply from…` là được. Nếu `Request timed out` → chưa nhận lời mời, hoặc Tailscale
   chưa bật (kiểm tra icon ở khay hệ thống, phải là **Connected**).

---

## 2. Cài uv (công cụ chạy MCP)

Mở **PowerShell**, chạy một trong hai cách:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

hoặc nếu máy có winget:

```powershell
winget install astral-sh.uv
```

Cài xong **đóng và mở lại PowerShell**, rồi kiểm tra:

```powershell
uv --version
```

### Cài MCP (một lần duy nhất)

```powershell
uv tool install --python 3.12 git+https://github.com/phuocnguyen1308-creator/vn-luat-mcp
where.exe vn-luat-mcp
```

Lệnh cuối in ra đường dẫn — thường là `C:\Users\<TEN_CUA_BAN>\.local\bin\vn-luat-mcp.exe`.
**Ghi lại đường dẫn này**, bước 3 cần dùng.

> **Vì sao cài cố định thay vì để `uvx` tải mỗi lần?** Cách `uvx --from git+...` tải lại mã nguồn
> từ GitHub mỗi lần Claude khởi động — trên Windows rất hay dính lỗi khóa file cache
> (`os error 32`). Cài một lần thì chạy thẳng, ổn định và khởi động nhanh hơn.
> Khi có bản cập nhật, chạy: `uv tool upgrade vn-luat-mcp`

---

## 3. Khai báo MCP vào Claude Desktop

1. Mở **File Explorer**, dán vào thanh địa chỉ rồi Enter:

   ```
   %APPDATA%\Claude
   ```

2. Mở `claude_desktop_config.json` bằng Notepad. *Nếu chưa có*, tạo file mới đúng tên đó.

3. Dán nội dung dưới đây. **Thay 3 chỗ**: đường dẫn `vn-luat-mcp.exe` (bước 2),
   `TEN_TAI_KHOAN_CUA_BAN` và `MAT_KHAU_DUOC_CAP` (quản trị gửi).

```json
{
  "mcpServers": {
    "luat": {
      "command": "C:\\Users\\TEN_CUA_BAN\\.local\\bin\\vn-luat-mcp.exe",
      "args": [],
      "env": {
        "PGHOST": "100.85.147.69",
        "PGPORT": "5432",
        "PGDATABASE": "appdb",
        "PGUSER": "TEN_TAI_KHOAN_CUA_BAN",
        "PGPASSWORD": "MAT_KHAU_DUOC_CAP",
        "E5_URL": "http://100.85.147.69:8899"
      }
    }
  }
}
```

> `PGUSER` là tên tài khoản **riêng** quản trị cấp cho bạn (vd `luat_ro_an`), **không phải**
> `mcp_ro` — đó là tài khoản của quản trị.

> **Đường dẫn Windows phải dùng hai gạch chéo ngược** `\\` như ví dụ.
> Nếu file đã có sẵn mục `mcpServers`, chỉ thêm khối `"luat": {...}` vào trong — đừng ghi đè cả file.

4. **Thoát hẳn Claude Desktop** (chuột phải icon khay hệ thống → **Quit**, không chỉ đóng cửa sổ),
   rồi mở lại.

---

## 4. Kiểm tra

Hỏi Claude: **"Kho luật có bao nhiêu điều?"**

Đúng thì Claude gọi `thong_ke` và trả về ~66.031 điều luật, 90 án lệ, 3.268 văn bản gốc.

Thử tra thật: *"Tra luật về an toàn thực phẩm"* · *"Điều 385 Bộ luật Dân sự quy định gì?"*

---

## 5. Bộ công cụ (12 tool)

**Luật thành văn (Bộ Pháp Điển)**
- `tra_luat` — tìm điều luật theo từ khóa (tham số `chu_de` để thu hẹp lĩnh vực)
- `xem_dieu_luat` — toàn văn một điều theo mã pháp điển (vd `9.1.LQ.385`)
- `liet_ke_chu_de` — danh sách 43 chủ đề
- `tra_thuat_ngu` — từ điển thuật ngữ pháp lý Việt–Anh

**Án lệ**
- `tra_an_le` — tìm án lệ / bản án (`loai='chinh_thuc'|'ban_an'|'cau'`)
- `xem_an_le` — toàn văn án lệ
- `liet_ke_an_le` — 90 án lệ chính thức

**Văn bản gốc (Công báo Chính phủ)**
- `nguon_cua_dieu` — từ điều pháp điển → **trích dẫn chuẩn** + cảnh báo điều đã bị sửa đổi
- `xem_van_ban_goc` — metadata chính thức + toàn văn theo số hiệu
- `tra_van_ban` — tìm trong toàn văn (chạm được phụ lục, biểu mẫu, căn cứ ban hành)

**Chung**
- `tim_ngu_nghia` — tìm theo ngữ nghĩa (hiểu ý câu hỏi dù không trùng từ khóa)
- `thong_ke` — đếm / thống kê kho

---

## 6. Mẹo dùng cho hiệu quả

- **Truy vấn ngắn 1–3 từ** cho kết quả tốt nhất. Câu dài bị loãng trọng số → có thể trả rỗng kèm gợi ý.
- **Nói rõ lĩnh vực** khi biết (vd *"tra luật về hợp đồng, chủ đề Dân sự"*) — thu hẹp từ 66k điều
  xuống vài trăm, chính xác hơn hẳn.
- **Gõ không dấu vẫn tìm được** (`thua ke` = `thừa kế`).
- **Cần trích dẫn chuẩn** → hỏi *"nguồn gốc của điều này"*, Claude sẽ trả dạng
  *"Điều 385 Bộ luật dân sự (số 91/2015/QH13)"* kèm cảnh báo nếu điều đã bị sửa đổi.

### ⚠️ Hai lĩnh vực KHÔNG có trong Bộ Pháp Điển

**Đất đai** và **Thi đua, khen thưởng** — Bộ Tư pháp chưa pháp điển hóa (chủ đề 11 và 29).
Tra bằng `tra_luat` sẽ **không ra gì** — đừng hiểu nhầm thành *"luật không quy định"*.

Với hai lĩnh vực này hãy hỏi Claude tra **văn bản gốc**, vd: *"tra văn bản gốc về bồi thường
khi thu hồi đất"*. Kho đã có Luật Đất đai 2024 + 6 nghị định/thông tư, và Luật Thi đua,
khen thưởng 2022 + nghị định + thông tư hướng dẫn.

### Độ tin cậy khi trích dẫn

- Nội dung **án lệ** trích từ OCR/Word — có thể sai vài ký tự. Trích dẫn chính thức phải
  đối chiếu PDF gốc (tool có kèm link).
- **Bộ Pháp Điển là bản hợp nhất để tra cứu**; hiệu lực pháp lý nằm ở **văn bản gốc**.
  Khi trích cho tài liệu chính thức, dùng `nguon_cua_dieu` để lấy số hiệu văn bản gốc,
  và kiểm tra văn bản còn hiệu lực không.

---

## 7. Xử lý sự cố

| Triệu chứng | Cách xử lý |
|---|---|
| Claude không thấy tool nào | Sai đường dẫn `uvx.exe` hoặc JSON sai cú pháp. Kiểm lại `where.exe uvx` và dấu `\\`. Thoát hẳn Claude rồi mở lại. |
| Báo **timeout** khi tra | Máy chủ đang tắt hoặc Tailscale rớt. Thử `ping 100.85.147.69`. |
| **password authentication failed** | Sai `PGUSER` hoặc `PGPASSWORD` — kiểm lại tên tài khoản quản trị cấp (không phải `mcp_ro`). Sửa xong phải **thoát hẳn** Claude rồi mở lại. |
| **connection refused / no pg_hba entry** | Máy chủ chưa cho phép IP của bạn — báo quản trị mở `pg_hba.conf` cho dải Tailscale. |
| `tim_ngu_nghia` báo không gọi được service nhúng | Dịch vụ tìm-theo-nghĩa trên máy chủ đang tắt. Báo quản trị; các tool khác vẫn dùng bình thường. |
| Log báo `Missing expected target directory for Python minor version link` | Thư mục Python của `uv` hỏng. Chạy: `uv cache clean` rồi `uv python install 3.12`, sau đó cài lại MCP. **Đừng** đặt `UV_PYTHON_INSTALL_DIR` trỏ vào gốc ổ `C:\` — không đủ quyền ghi. |
| Log báo `failed to remove directory ... (os error 32)` | File bị khóa bởi tiến trình cũ. Thoát hẳn Claude, rồi `Get-Process uv,uvx,python \| Stop-Process -Force`, `uv cache clean`, cài lại. Nếu tái diễn → phần mềm diệt virus đang quét; thêm ngoại lệ cho `%LOCALAPPDATA%\uv` và `%APPDATA%\uv`. |
| **Failed to start Claude's workspace / VM service not running** | **Không liên quan MCP này** — đó là máy ảo riêng của Claude cho việc chạy code. Tra cứu luật vẫn hoạt động bình thường. Muốn sửa: khởi động lại máy; kiểm tra **Virtualization = Enabled** trong Task Manager → Performance → CPU; hoặc `wsl --install` + `wsl --update`. |

**Bảo mật:** mật khẩu nằm trong file cấu hình dạng văn bản thường. Đừng chia sẻ file này hoặc
chụp màn hình có mật khẩu. Tài khoản của bạn chỉ **đọc được dữ liệu luật** — không đọc được
database khác trên máy chủ, không sửa/xoá được gì.

Nếu nghi mật khẩu bị lộ, báo quản trị: họ đổi mật khẩu **riêng tài khoản của bạn**, các thành
viên khác không bị ảnh hưởng.
