#!/usr/bin/env python3
"""MCP server "luat": tra cứu PHÁP LUẬT Việt Nam trong PostgreSQL.
Gộp 2 nguồn: Bộ Pháp Điển (luật thành văn) + Án Lệ/bản án (toaan.gov.vn).
Tra bằng full-text; Claude tự mở rộng từ khóa + xếp hạng để đạt hiệu quả ngữ nghĩa."""
from mcp.server.fastmcp import FastMCP
from .db import query

mcp = FastMCP("luat")

SOURCE_URL = ("'https://phapdien.moj.gov.vn/TraCuuPhapDien/ViewBoPD.aspx?obj=&demucid=' "
              "|| a.subject_id || '&mapc=1' || a.article_anchor")

# ─────────────────────────── LUẬT THÀNH VĂN (phapdien) ───────────────────────────

@mcp.tool()
def tra_luat(tu_khoa: str, gioi_han: int = 10) -> list:
    """Tìm ĐIỀU LUẬT (luật thành văn) theo từ khóa (full-text, tìm cả khi gõ không dấu).
    Mẹo: gọi nhiều biến thể từ khóa/đồng nghĩa rồi tự chọn lọc để phủ ngữ nghĩa tốt hơn.
    Trả về tiêu đề, chương, chủ đề, trích đoạn và link nguồn."""
    return query(f"""
        SELECT a.article_anchor, a.article_title, ch.chapter_title, s.topic_title,
               ts_headline('simple', left(a.content_text, 4000),
                    plainto_tsquery('simple', unaccent(%s)),
                    'StartSel=[, StopSel=], MaxFragments=1, MaxWords=25, MinWords=10') AS trich_doan,
               {SOURCE_URL} AS source_url
        FROM articles a
        LEFT JOIN chapters ch ON ch.chapter_id = a.chapter_id
        LEFT JOIN subjects s ON s.subject_id = a.subject_id
        WHERE a.search_vector @@ plainto_tsquery('simple', unaccent(%s))
        ORDER BY ts_rank(a.search_vector, plainto_tsquery('simple', unaccent(%s))) DESC
        LIMIT %s
    """, (tu_khoa, tu_khoa, tu_khoa, gioi_han))


@mcp.tool()
def xem_dieu_luat(article_anchor: str) -> dict:
    """Xem toàn văn một điều luật theo mã anchor (vd '2.2.TT.15.2')."""
    rows = query(f"""
        SELECT a.article_anchor, a.article_title, ch.chapter_title, s.topic_title,
               a.content_text, a.source_note_text, a.related_note_text,
               {SOURCE_URL} AS source_url
        FROM articles a
        LEFT JOIN chapters ch ON ch.chapter_id = a.chapter_id
        LEFT JOIN subjects s ON s.subject_id = a.subject_id
        WHERE a.article_anchor = %s LIMIT 1
    """, (article_anchor,))
    return rows[0] if rows else {"error": "Không tìm thấy điều luật"}


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
def tra_an_le(tu_khoa: str, gioi_han: int = 10) -> list:
    """Tìm BẢN ÁN / ÁN LỆ theo từ khóa (full-text, tìm cả khi gõ không dấu).
    Trả về số án lệ, tiêu đề, cấp tòa, năm, trích đoạn nguyên tắc, link."""
    return query("""
        SELECT precedent_number, title, court_level, year, case_type,
               ts_headline('simple', coalesce(nullif(principle_text,''), left(markdown, 4000)),
                    plainto_tsquery('simple', unaccent(%s)),
                    'StartSel=[, StopSel=], MaxFragments=1, MaxWords=35, MinWords=12') AS trich_doan,
               detail_url, pdf_url
        FROM anle_documents
        WHERE search_vector @@ plainto_tsquery('simple', unaccent(%s))
        ORDER BY ts_rank(search_vector, plainto_tsquery('simple', unaccent(%s))) DESC
        LIMIT %s
    """, (tu_khoa, tu_khoa, tu_khoa, gioi_han))


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
    return query("""SELECT s.precedent_number, s.court_level, s.year, s.text
                    FROM anle_sentences s
                    WHERE unaccent(lower(s.text)) LIKE unaccent(lower(%s)) LIMIT %s""",
                 (f"%{tu_khoa}%", gioi_han))


def main():
    """Entry point cho console script / uvx."""
    mcp.run()


if __name__ == "__main__":
    main()
