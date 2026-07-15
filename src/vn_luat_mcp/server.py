#!/usr/bin/env python3
"""MCP server "luat": tra cứu PHÁP LUẬT Việt Nam trong PostgreSQL.
Gộp 2 nguồn: Bộ Pháp Điển (luật thành văn) + Án Lệ/bản án (toaan.gov.vn).
Tra bằng full-text; Claude tự mở rộng từ khóa + xếp hạng để đạt hiệu quả ngữ nghĩa."""
import re
from mcp.server.fastmcp import FastMCP
from .db import query

mcp = FastMCP("luat")

SOURCE_URL = ("'https://phapdien.moj.gov.vn/TraCuuPhapDien/ViewBoPD.aspx?obj=&demucid=' "
              "|| a.subject_id || '&mapc=1' || a.article_anchor")

# ─────────────────────────── LUẬT THÀNH VĂN (phapdien) ───────────────────────────

def _shape(rows, offset):
    """Bọc kết quả kèm metadata phân trang. rows phải có cột _total (count OVER())."""
    total = rows[0]["_total"] if rows else 0
    for r in rows:
        r.pop("_total", None)
    return {"tong_so": total, "offset": offset, "so_tra": len(rows),
            "con_nua": offset + len(rows) < total, "ket_qua": rows}


@mcp.tool()
def tra_luat(tu_khoa: str, gioi_han: int = 10, offset: int = 0) -> dict:
    """Tìm ĐIỀU LUẬT (luật thành văn) theo từ khóa (full-text, tìm cả khi gõ không dấu).
    Phân trang: gioi_han tối đa 50; dùng offset để lấy trang kế (offset=10 lấy trang 2...).
    Mẹo: câu càng NGẮN & đúng từ khóa càng chuẩn; kết quả lạc chủ đề thì thử tra_luat_theo_chu_de.
    Trả về {tong_so, offset, so_tra, con_nua, ket_qua[...]}."""
    gioi_han = max(1, min(int(gioi_han), 50))
    offset = max(0, int(offset))
    rows = query(f"""
        SELECT count(*) OVER() AS _total,
               a.article_anchor, a.ma_phap_dien, a.article_title, ch.chapter_title, s.topic_title,
               ts_headline('simple', left(a.content_text, 4000),
                    plainto_tsquery('simple', unaccent(%s)),
                    'StartSel=[, StopSel=], MaxFragments=1, MaxWords=25, MinWords=10') AS trich_doan,
               {SOURCE_URL} AS source_url
        FROM articles a
        LEFT JOIN chapters ch ON ch.chapter_id = a.chapter_id
        LEFT JOIN subjects s ON s.subject_id = a.subject_id
        WHERE a.search_vector @@ plainto_tsquery('simple', unaccent(%s))
        ORDER BY ts_rank(a.search_vector, plainto_tsquery('simple', unaccent(%s))) DESC
        LIMIT %s OFFSET %s
    """, (tu_khoa, tu_khoa, tu_khoa, gioi_han, offset))
    return _shape(rows, offset)


# Mã pháp điển nằm trong article_title, vd "Điều 9.1.LQ.623. ..." -> "9.1.LQ.623"
_MA_PAT = r"Điều\s+(\d+\.\d+\.[A-ZĐ]+(?:\.\d+)+)"


@mcp.tool()
def xem_dieu_luat(ma_dieu: str) -> dict:
    """Xem toàn văn một điều luật. Nhận CẢ BA dạng, tự nhận diện:
      • Mã pháp điển: '9.1.LQ.623' (hoặc có tiền tố 'Điều 9.1.LQ.623')
      • Anchor số có dấu #: '#0900...'
      • Anchor số không dấu #: '0900...'
    Nếu một mã ứng với nhiều điều, trả về danh sách ứng viên kèm anchor để chọn lại."""
    s = (ma_dieu or "").strip()
    base = f"""
        SELECT a.article_anchor, a.ma_phap_dien, a.article_title, ch.chapter_title,
               s.topic_title, a.content_text, a.source_note_text, a.related_note_text,
               {SOURCE_URL} AS source_url
        FROM articles a
        LEFT JOIN chapters ch ON ch.chapter_id = a.chapter_id
        LEFT JOIN subjects s ON s.subject_id = a.subject_id
    """
    digits = s.lstrip("#")
    if digits.isdigit() and len(digits) >= 20:          # anchor số
        rows = query(base + " WHERE a.article_anchor = %s LIMIT 5", ("#" + digits,))
    else:                                                # mã pháp điển
        code = re.sub(r"^\s*Điều\s+", "", s).strip().rstrip(".")
        rows = query(base + " WHERE a.ma_phap_dien = %s LIMIT 5", (code,))
    if not rows:
        return {"error": "Không tìm thấy điều luật",
                "goi_y": "Kiểm tra lại mã, hoặc dùng tra_luat để tìm theo từ khóa."}
    if len(rows) > 1:
        return {"canh_bao": f"Mã ứng với {len(rows)} điều — chọn anchor cụ thể rồi gọi lại:",
                "ung_vien": [{"article_title": r["article_title"],
                              "article_anchor": r["article_anchor"]} for r in rows]}
    return rows[0]


@mcp.tool()
def liet_ke_chu_de() -> list:
    """Liệt kê các chủ đề (topic) và số đề mục trong Bộ Pháp Điển."""
    return query("""SELECT topic_title_vi, topic_title_en, article_count, demuc_count
                    FROM ontology_topics ORDER BY topic_number""")


@mcp.tool()
def tra_thuat_ngu(tu: str, gioi_han: int = 15) -> list:
    """Tra từ điển thuật ngữ pháp lý Việt–Anh."""
    return query("""SELECT category, vi, en, note FROM ontology_glossary
                    WHERE unaccent(lower(vi)) LIKE unaccent(lower(%s)) OR lower(en) LIKE lower(%s)
                    LIMIT %s""", (f"%{tu}%", f"%{tu}%", gioi_han))


@mcp.tool()
def tra_luat_theo_chu_de(tu_khoa: str, chu_de: str, gioi_han: int = 10) -> list:
    """Tìm điều luật trong PHẠM VI một chủ đề. chu_de: khớp gần đúng tên chủ đề (topic_title)."""
    return query("""
        SELECT a.article_anchor, a.article_title, s.topic_title,
               ts_headline('simple', left(a.content_text, 4000),
                    plainto_tsquery('simple', unaccent(%s)),
                    'StartSel=[, StopSel=], MaxWords=45, MinWords=18') AS trich_doan
        FROM articles a
        JOIN subjects s ON s.subject_id = a.subject_id
        WHERE a.search_vector @@ plainto_tsquery('simple', unaccent(%s))
          AND unaccent(s.topic_title) ILIKE unaccent(%s)
        ORDER BY ts_rank(a.search_vector, plainto_tsquery('simple', unaccent(%s))) DESC
        LIMIT %s
    """, (tu_khoa, tu_khoa, f"%{chu_de}%", tu_khoa, gioi_han))

# ─────────────────────────────── ÁN LỆ (anle) ───────────────────────────────

@mcp.tool()
def tra_an_le(tu_khoa: str, gioi_han: int = 10, offset: int = 0) -> dict:
    """Tìm BẢN ÁN / ÁN LỆ theo từ khóa (full-text, tìm cả khi gõ không dấu).
    Phân trang: gioi_han tối đa 50; dùng offset để lấy trang kế.
    Trả về {tong_so, offset, so_tra, con_nua, ket_qua[...]}."""
    gioi_han = max(1, min(int(gioi_han), 50))
    offset = max(0, int(offset))
    rows = query("""
        SELECT count(*) OVER() AS _total,
               precedent_number, title, court_level, year, case_type,
               ts_headline('simple', coalesce(nullif(principle_text,''), left(markdown, 4000)),
                    plainto_tsquery('simple', unaccent(%s)),
                    'StartSel=[, StopSel=], MaxFragments=1, MaxWords=35, MinWords=12') AS trich_doan,
               detail_url, pdf_url
        FROM anle_documents
        WHERE search_vector @@ plainto_tsquery('simple', unaccent(%s))
        ORDER BY ts_rank(search_vector, plainto_tsquery('simple', unaccent(%s))) DESC
        LIMIT %s OFFSET %s
    """, (tu_khoa, tu_khoa, tu_khoa, gioi_han, offset))
    return _shape(rows, offset)


@mcp.tool()
def xem_an_le(dinh_danh: str) -> dict:
    """Xem toàn văn một bản án theo số án lệ (precedent_number) hoặc doc_name."""
    rows = query("""
        SELECT precedent_number, title, court_level, year, case_type, issuing_authority,
               adopted_date, subject, principle_text, markdown, detail_url, pdf_url,
               applied_article_code, applied_article_number, applied_article_clause
        FROM anle_documents WHERE precedent_number = %s OR doc_name = %s LIMIT 1
    """, (dinh_danh, dinh_danh))
    return rows[0] if rows else {"error": "Không tìm thấy án lệ"}


@mcp.tool()
def an_le_theo_dieu_luat(applied_article_code: str, so_dieu: int = None, gioi_han: int = 20) -> list:
    """Tìm các án lệ ÁP DỤNG một điều luật (bắc cầu án lệ ↔ luật thành văn).
    applied_article_code: mã bộ luật/văn bản; so_dieu: số điều (tùy chọn)."""
    if so_dieu is None:
        return query("""SELECT precedent_number, title, court_level, year,
                        applied_article_code, applied_article_number, applied_article_clause, detail_url
                        FROM anle_documents WHERE applied_article_code = %s
                        ORDER BY year DESC LIMIT %s""", (applied_article_code, gioi_han))
    return query("""SELECT precedent_number, title, court_level, year,
                    applied_article_code, applied_article_number, applied_article_clause, detail_url
                    FROM anle_documents WHERE applied_article_code = %s AND applied_article_number = %s
                    ORDER BY year DESC LIMIT %s""", (applied_article_code, so_dieu, gioi_han))


@mcp.tool()
def tra_cau_an_le(tu_khoa: str, gioi_han: int = 15) -> list:
    """Tìm ở cấp CÂU trong bản án (chi tiết hơn) — trả câu khớp kèm số án lệ nguồn."""
    gioi_han = max(1, min(int(gioi_han), 50))
    return query("""SELECT s.precedent_number, s.court_level, s.year, s.text
                    FROM anle_sentences s
                    WHERE unaccent(lower(s.text)) LIKE unaccent(lower(%s)) LIMIT %s""",
                 (f"%{tu_khoa}%", gioi_han))


@mcp.tool()
def liet_ke_an_le() -> dict:
    """Liệt kê các ÁN LỆ CHÍNH THỨC được tham chiếu trong kho (kèm số bản án minh họa & khoảng năm).
    LƯU Ý: kho chỉ chứa 19 trong số ~70+ án lệ chính thức của VN, và KHÔNG theo dõi trạng thái
    hiệu lực — phải kiểm tra lại trên toaan.gov.vn trước khi viện dẫn."""
    rows = query("""SELECT precedent_number AS an_le, count(*) AS so_ban_an,
                    min(year) AS nam_som, max(year) AS nam_moi
                    FROM anle_documents
                    WHERE precedent_number IS NOT NULL AND precedent_number <> ''
                    GROUP BY precedent_number ORDER BY precedent_number""")
    return {"canh_bao": "Chỉ 19/≈70+ án lệ chính thức có trong kho; CHƯA theo dõi hiệu lực — "
                        "kiểm tra toaan.gov.vn trước khi viện dẫn.",
            "so_an_le": len(rows), "ket_qua": rows}


# ─────────────────────────────── THỐNG KÊ ───────────────────────────────

@mcp.tool()
def thong_ke(loai: str = "tong_quan", nhom_theo: str = None) -> dict:
    """Đếm/thống kê số lượng trong kho dữ liệu.
      loai='tong_quan'                              → tổng điều luật / chủ đề / bản án / án lệ.
      loai='dieu_luat', nhom_theo='chu_de'          → số điều luật theo từng chủ đề.
      loai='ban_an', nhom_theo='linh_vuc'|'nam'|'toa' → phân bố bản án."""
    if loai == "dieu_luat":
        rows = query("""SELECT topic_number, topic_title_vi AS chu_de,
                        article_count AS so_dieu, demuc_count AS so_de_muc
                        FROM ontology_topics ORDER BY article_count DESC""")
        return {"loai": "dieu_luat theo chu_de", "so_chu_de": len(rows), "ket_qua": rows}
    if loai in ("ban_an", "an_le"):
        col = {"linh_vuc": "case_type", "nam": "year", "toa": "court_level"}.get(nhom_theo)
        if col:
            rows = query(f"""SELECT COALESCE(NULLIF({col}::text, ''), '(không rõ)') AS nhom,
                            count(*) AS so_luong FROM anle_documents GROUP BY 1 ORDER BY 2 DESC""")
            return {"loai": f"ban_an theo {nhom_theo}", "ket_qua": rows}
        rows = query("""SELECT count(*) AS tong_ban_an,
                        count(DISTINCT precedent_number) AS an_le_chinh_thuc,
                        min(year) AS nam_som_nhat, max(year) AS nam_moi_nhat
                        FROM anle_documents""")
        return {"loai": "an_le tong_quan", **(rows[0] if rows else {})}
    # tong_quan
    dl = query("SELECT count(*) AS c FROM articles")[0]["c"]
    cd = query("SELECT count(DISTINCT topic_title) AS c FROM subjects")[0]["c"]
    ba = query("SELECT count(*) AS c FROM anle_documents")[0]["c"]
    al = query("SELECT count(DISTINCT precedent_number) AS c FROM anle_documents "
               "WHERE precedent_number <> ''")[0]["c"]
    return {"dieu_luat": dl, "chu_de": cd, "ban_an": ba, "an_le_chinh_thuc": al,
            "ghi_chu": "Kho án lệ chủ yếu là BẢN ÁN; chỉ 19 án lệ chính thức được tham chiếu."}


def main():
    """Entry point cho console script / uvx."""
    mcp.run()


if __name__ == "__main__":
    main()
