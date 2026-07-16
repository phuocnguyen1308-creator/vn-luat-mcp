#!/usr/bin/env python3
"""MCP server "luat": tra cứu PHÁP LUẬT Việt Nam trong PostgreSQL.
Gộp 2 nguồn: Bộ Pháp Điển (luật thành văn) + Án Lệ/bản án (toaan.gov.vn).
Tra bằng full-text; Claude tự mở rộng từ khóa + xếp hạng để đạt hiệu quả ngữ nghĩa."""
import re, os, json, urllib.request
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


NGUONG_DIEM = 0.05  # điểm cao nhất dưới mức này = khớp yếu/rải rác -> trả rỗng thay vì rác

# Trọng số ts_rank_cd theo hạng D,C,B,A: tiêu đề (A)=1.0 áp đảo nội dung (B)=0.4
_RANK_W = "'{0.1, 0.2, 0.4, 1.0}'"


@mcp.tool()
def tra_luat(tu_khoa: str, gioi_han: int = 10, offset: int = 0, chu_de: str = None) -> dict:
    """Tìm ĐIỀU LUẬT (luật thành văn) theo từ khóa (full-text, tìm cả khi gõ không dấu).
    Xếp hạng ƯU TIÊN khớp ở TIÊU ĐỀ; mỗi kết quả kèm 'diem' (độ liên quan).
    chu_de (tùy chọn): tên chủ đề để thu hẹp & tăng chính xác, vd 'Dân sự'.
    Phân trang: gioi_han tối đa 50; offset để lấy trang kế.
    LƯU Ý: câu càng NGẮN & đúng thuật ngữ càng chuẩn. Câu dài/mô tả sẽ cho điểm thấp và
    CÓ THỂ TRẢ RỖNG — khi đó rút gọn còn từ khóa cốt lõi (vd 'hợp đồng', 'thừa kế') hoặc thêm chu_de.
    Trả về {tong_so, offset, so_tra, con_nua, ket_qua[...]}; hoặc rỗng kèm goi_y nếu khớp quá yếu."""
    gioi_han = max(1, min(int(gioi_han), 50))
    offset = max(0, int(offset))
    cond, params = "", [tu_khoa, tu_khoa, tu_khoa]      # diem, headline, where
    if chu_de:
        cond = " AND unaccent(s.topic_title) ILIKE unaccent(%s)"
        params.append("%" + chu_de + "%")
    params += [gioi_han, offset]
    rows = query(f"""
        SELECT count(*) OVER() AS _total,
               round(ts_rank_cd({_RANK_W}, a.search_vector,
                     plainto_tsquery('simple', unaccent(%s)))::numeric, 4)::float8 AS diem,
               a.article_anchor, a.ma_phap_dien, a.article_title,
               left(ch.chapter_title, 140) AS chapter_title, s.topic_title,
               ts_headline('vi_unaccent', left(a.content_text, 4000),
                    plainto_tsquery('vi_unaccent', %s),
                    'StartSel=«, StopSel=», MaxFragments=1, MaxWords=25, MinWords=10') AS trich_doan,
               {SOURCE_URL} AS source_url
        FROM articles a
        LEFT JOIN chapters ch ON ch.chapter_id = a.chapter_id
        LEFT JOIN subjects s ON s.subject_id = a.subject_id
        WHERE a.search_vector @@ plainto_tsquery('simple', unaccent(%s)){cond}
        ORDER BY diem DESC
        LIMIT %s OFFSET %s
    """, tuple(params))
    if rows and offset == 0 and not chu_de and rows[0]["diem"] < NGUONG_DIEM:
        total = rows[0]["_total"]
        return {"tong_so": total, "so_tra": 0, "ket_qua": [],
                "canh_bao": f"Khớp yếu (điểm cao nhất {rows[0]['diem']}): {total} điều chứa rải rác "
                            "các từ nhưng không sát chủ đề.",
                "goi_y": "Rút gọn còn thuật ngữ cốt lõi (vd 'hợp đồng', 'thừa kế'), thêm "
                         "chu_de='Dân sự', hoặc dùng tra_luat_theo_chu_de."}
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
    r = dict(rows[0])
    ct = r.get("content_text") or ""
    if len(ct) > 20000:                                  # tránh bom token với điều luật khổng lồ
        r["content_text"] = ct[:20000] + f"\n…[điều luật dài {len(ct):,} ký tự — đã cắt; xem đầy đủ tại source_url]"
    return r


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
    """Tìm điều luật trong PHẠM VI một chủ đề (chính xác hơn tra_luat cho câu chung/dài).
    chu_de: khớp gần đúng tên chủ đề (topic_title), vd 'Dân sự'. Mỗi kết quả kèm 'diem'."""
    gioi_han = max(1, min(int(gioi_han), 50))
    return query(f"""
        SELECT a.article_anchor, a.ma_phap_dien, a.article_title, s.topic_title,
               round(ts_rank_cd({_RANK_W}, a.search_vector,
                     plainto_tsquery('simple', unaccent(%s)))::numeric, 4)::float8 AS diem,
               ts_headline('vi_unaccent', left(a.content_text, 4000),
                    plainto_tsquery('vi_unaccent', %s),
                    'StartSel=«, StopSel=», MaxWords=45, MinWords=18') AS trich_doan
        FROM articles a
        JOIN subjects s ON s.subject_id = a.subject_id
        WHERE a.search_vector @@ plainto_tsquery('simple', unaccent(%s))
          AND unaccent(s.topic_title) ILIKE unaccent(%s)
        ORDER BY diem DESC
        LIMIT %s
    """, (tu_khoa, tu_khoa, tu_khoa, f"%{chu_de}%", gioi_han))

# ─────────────────────────────── ÁN LỆ (anle) ───────────────────────────────

@mcp.tool()
def tra_an_le(tu_khoa: str, gioi_han: int = 10, offset: int = 0) -> dict:
    """Tìm BẢN ÁN / ÁN LỆ theo từ khóa (full-text). Xếp hạng ưu tiên tiêu đề/nguyên tắc; kèm 'diem'.
    Cũng dùng để tìm án lệ nhắc tới một luật (gõ tên luật). Phân trang: gioi_han tối đa 50, offset.
    Câu quá mơ hồ → có thể trả rỗng + gợi ý. Trả về {tong_so, offset, so_tra, con_nua, ket_qua[...]}."""
    gioi_han = max(1, min(int(gioi_han), 50))
    offset = max(0, int(offset))
    rows = query(f"""
        SELECT count(*) OVER() AS _total,
               round(ts_rank_cd({_RANK_W}, search_vector,
                     plainto_tsquery('simple', unaccent(%s)))::numeric, 4)::float8 AS diem,
               precedent_number, title, court_level, year, case_type,
               ts_headline('vi_unaccent',
                    regexp_replace(left(coalesce(nullif(principle_text,''), markdown), 150000),
                             '##\\s*Page\\s*[0-9]+', ' ', 'g'),
                    plainto_tsquery('vi_unaccent', %s),
                    'StartSel=«, StopSel=», MaxFragments=1, MaxWords=30, MinWords=12') AS trich_doan,
               detail_url
        FROM anle_documents
        WHERE search_vector @@ plainto_tsquery('simple', unaccent(%s))
        ORDER BY diem DESC
        LIMIT %s OFFSET %s
    """, (tu_khoa, tu_khoa, tu_khoa, gioi_han, offset))
    if rows and offset == 0 and rows[0]["diem"] < 0.02:
        total = rows[0]["_total"]
        return {"tong_so": total, "so_tra": 0, "ket_qua": [],
                "canh_bao": f"Khớp yếu (điểm cao nhất {rows[0]['diem']}).",
                "goi_y": "Rút gọn còn từ khóa cốt lõi, hoặc lọc theo lĩnh vực bằng thong_ke."}
    return _shape(rows, offset)


@mcp.tool()
def xem_an_le(dinh_danh: str, day_du: bool = False) -> dict:
    """Xem một bản án theo số án lệ (precedent_number) hoặc doc_name.
    MẶC ĐỊNH trả metadata + trích đoạn đầu (~1500 ký tự) + link; đặt day_du=True để lấy TOÀN VĂN.
    Nếu một số án lệ ứng NHIỀU bản án minh họa, trả danh sách để chọn bằng doc_name."""
    rows = query("""
        SELECT doc_name, precedent_number, title, court_level, year, case_type,
               issuing_authority, adopted_date, subject, principle_text, markdown,
               detail_url, applied_article_number
        FROM anle_documents WHERE precedent_number = %s OR doc_name = %s
        ORDER BY year DESC LIMIT 30
    """, (dinh_danh, dinh_danh))
    if not rows:
        return {"error": "Không tìm thấy án lệ", "goi_y": "Thử tra_an_le để tìm theo từ khóa."}
    if len(rows) > 1:
        return {"canh_bao": f"'{dinh_danh}' ứng với {len(rows)} bản án minh họa — chọn doc_name cụ thể rồi gọi lại:",
                "ung_vien": [{"doc_name": r["doc_name"], "title": r["title"],
                              "nam": r["year"], "toa": r["court_level"]} for r in rows]}
    r = dict(rows[0])
    md = r.get("markdown") or ""
    if not day_du and len(md) > 1500:
        r["markdown"] = md[:1500] + f"\n…[bản án dài {len(md):,} ký tự — đã cắt. Gọi lại day_du=true để xem toàn văn, hoặc mở detail_url]"
    return r


@mcp.tool()
def tra_cau_an_le(tu_khoa: str, gioi_han: int = 15, offset: int = 0) -> dict:
    """Tìm ở cấp CÂU trong bản án (chi tiết hơn) — full-text (nhanh), trả câu khớp kèm số án lệ nguồn.
    Phân trang: gioi_han tối đa 50, offset. Trả về {tong_so, offset, so_tra, con_nua, ket_qua[...]}."""
    gioi_han = max(1, min(int(gioi_han), 50))
    offset = max(0, int(offset))
    rows = query("""
        SELECT count(*) OVER() AS _total, s.precedent_number, s.court_level, s.year, s.text
        FROM anle_sentences s
        WHERE s.search_vector @@ plainto_tsquery('simple', unaccent(%s))
        LIMIT %s OFFSET %s
    """, (tu_khoa, gioi_han, offset))
    return _shape(rows, offset)


@mcp.tool()
def liet_ke_an_le(nam: int = None, gioi_han: int = 100) -> dict:
    """Liệt kê 90 ÁN LỆ CHÍNH THỨC của Việt Nam (số + tiêu đề + năm + số bản án minh họa trong kho).
    Lọc theo năm nếu cần. Toàn văn: xem_an_le_ct; tìm theo từ khóa: tra_an_le_ct."""
    cond, params = "", []
    if nam:
        cond = " WHERE ct.nam = %s"; params.append(int(nam))
    params.append(min(int(gioi_han), 100))
    rows = query(f"""
        SELECT ct.so, ct.nam, ct.tieu_de,
               (SELECT count(*) FROM anle_documents d
                WHERE d.precedent_number = 'Án lệ số ' || ct.so) AS so_ban_an_minh_hoa
        FROM an_le_chinh_thuc ct{cond}
        ORDER BY ct.so_thu_tu DESC LIMIT %s""", tuple(params))
    return {"tong_so": len(rows),
            "ghi_chu": "90 án lệ chính thức. Nội dung từ OCR/Word — đối chiếu PDF gốc khi cần chính xác.",
            "ket_qua": rows}


@mcp.tool()
def tra_an_le_ct(tu_khoa: str, gioi_han: int = 10, offset: int = 0) -> dict:
    """Tìm trong 90 ÁN LỆ CHÍNH THỨC theo từ khóa (full-text nội dung + tiêu đề, giữ dấu, khớp cả không dấu).
    Trả về số, tiêu đề, năm, trích đoạn, link PDF, 'diem'. Phân trang gioi_han≤50, offset.
    Câu quá mơ hồ → có thể trả rỗng + gợi ý."""
    gioi_han = max(1, min(int(gioi_han), 50)); offset = max(0, int(offset))
    rows = query(f"""
        SELECT count(*) OVER() AS _total,
               round(ts_rank_cd({_RANK_W}, search_vector,
                     plainto_tsquery('vi_unaccent', %s))::numeric, 4)::float8 AS diem,
               so, nam, tieu_de,
               ts_headline('vi_unaccent', left(noi_dung, 200000),
                    plainto_tsquery('vi_unaccent', %s),
                    'StartSel=«, StopSel=», MaxFragments=2, MaxWords=30, MinWords=12') AS trich_doan,
               pdf_url
        FROM an_le_chinh_thuc
        WHERE search_vector @@ plainto_tsquery('vi_unaccent', %s)
        ORDER BY diem DESC LIMIT %s OFFSET %s
    """, (tu_khoa, tu_khoa, tu_khoa, gioi_han, offset))
    if rows and offset == 0 and rows[0]["diem"] < 0.02:
        return {"tong_so": rows[0]["_total"], "so_tra": 0, "ket_qua": [],
                "goi_y": "Khớp yếu — rút gọn còn từ khóa cốt lõi, hoặc dùng liet_ke_an_le."}
    return _shape(rows, offset)


@mcp.tool()
def xem_an_le_ct(so: str, day_du: bool = False) -> dict:
    """Xem một ÁN LỆ CHÍNH THỨC theo số (vd '03/2016/AL' hoặc 'Án lệ số 03/2016/AL').
    Mặc định trả tiêu đề + ~3000 ký tự đầu + link PDF; day_du=True để lấy TOÀN VĂN."""
    s = re.sub(r"^\s*[Áá]n\s*lệ\s*số\s*", "", (so or "").strip())
    rows = query("SELECT so, nam, tieu_de, noi_dung, pdf_url FROM an_le_chinh_thuc WHERE so = %s", (s,))
    if not rows:
        return {"error": "Không tìm thấy án lệ",
                "goi_y": "Dùng liet_ke_an_le xem danh sách, hoặc tra_an_le_ct tìm theo từ khóa."}
    r = dict(rows[0]); nd = r.get("noi_dung") or ""
    if not day_du and len(nd) > 3000:
        r["noi_dung"] = nd[:3000] + f"\n…[án lệ dài {len(nd):,} ký tự — đã cắt. Gọi day_du=true để toàn văn, hoặc mở pdf_url]"
    r["ghi_chu"] = "Nội dung từ OCR/Word — có thể có lỗi nhận dạng; đối chiếu PDF gốc khi cần chính xác."
    return r


# ──────────────── TÌM NGỮ NGHĨA (pgvector + service nhúng trên Pi) ────────────────

E5_URL = os.environ.get("E5_URL", "http://100.85.147.69:8899")

def _nhung_cau_hoi(text):
    """Gọi service nhúng trên Pi → vector 384-dim."""
    body = json.dumps({"texts": [text], "prefix": "query"}).encode()
    req = urllib.request.Request(E5_URL + "/embed", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())["vectors"][0]

def _vstr(v):
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"

def _rrf(danh_sach, k0=60):
    """Weighted Reciprocal Rank Fusion. danh_sach: list các (danh_sách_khóa, trọng_số).
    Vector nên có trọng số cao hơn FTS để câu mô tả không bị FTS kéo mục nhiễu lên."""
    diem = {}
    for lst, w in danh_sach:
        for hang, khoa in enumerate(lst):
            diem[khoa] = diem.get(khoa, 0.0) + w / (k0 + hang)
    return sorted(diem, key=diem.get, reverse=True)


@mcp.tool()
def tim_ngu_nghia(cau_hoi: str, gioi_han: int = 5, nguon: str = "an_le") -> dict:
    """Tìm theo NGỮ NGHĨA (semantic) — hiểu ý câu hỏi kể cả khi không trùng từ khóa.
    Kết hợp vector (pgvector, model đa ngôn ngữ) + full-text, gộp bằng RRF.
    nguon: 'an_le' (90 án lệ chính thức, mặc định) hoặc 'dieu_luat' (điều luật thành văn).
    Hợp khi câu hỏi MÔ TẢ tình huống đời thường (vd 'mua nhà trả góp rồi không trả được thì sao',
    'vợ chồng trúng số chia thế nào'). Với truy vấn đúng thuật ngữ/số điều, tra_luat/tra_an_le_ct vẫn tốt.
    Trả về {tong_so, ket_qua:[...]} — mỗi mục có do_tuong_dong, trich_doan + khóa tra cứu (so/ma_phap_dien)."""
    gioi_han = max(1, min(int(gioi_han), 20))
    cau_hoi = (cau_hoi or "").strip()
    if not cau_hoi:
        return {"error": "Câu hỏi rỗng."}
    if nguon not in ("an_le", "dieu_luat"):
        return {"error": "nguon phải là 'an_le' hoặc 'dieu_luat'."}
    try:
        vec = _vstr(_nhung_cau_hoi(cau_hoi))
    except Exception as e:
        return {"error": f"Không gọi được service nhúng ({e}).",
                "goi_y": "Kiểm tra 'systemctl status embed' trên Pi, hoặc dùng tra_luat/tra_an_le_ct."}
    # 1) Vector: 60 đoạn gần nhất, gom theo tài liệu giữ đoạn khớp nhất
    chunks = query("""
        SELECT ref_id, doan, 1 - (embedding <=> %s::vector) AS sim
        FROM doc_embeddings WHERE nguon = %s
        ORDER BY embedding <=> %s::vector LIMIT 60
    """, (vec, nguon, vec))
    if not chunks:
        return {"tong_so": 0, "ket_qua": [],
                "goi_y": f"Chưa có vector cho nguon='{nguon}' (có thể đang nhúng). Dùng tra_luat/tra_an_le_ct."}
    best = {}
    for c in chunks:
        if c["ref_id"] not in best or c["sim"] > best[c["ref_id"]][0]:
            best[c["ref_id"]] = (c["sim"], c["doan"])
    vec_order = sorted(best, key=lambda s: best[s][0], reverse=True)
    # 2) Full-text + 3) RRF + 4) bổ sung metadata — tùy nguồn
    if nguon == "an_le":
        fts = query(f"""SELECT so AS k, ts_rank_cd({_RANK_W}, search_vector,
                        plainto_tsquery('vi_unaccent', %s)) AS diem
                        FROM an_le_chinh_thuc
                        WHERE search_vector @@ plainto_tsquery('vi_unaccent', %s)
                        ORDER BY diem DESC LIMIT 60""", (cau_hoi, cau_hoi))
        final = _rrf([(vec_order, 1.0), ([r["k"] for r in fts][:25], 0.5)])[:gioi_han]
        meta = {r["so"]: r for r in query(
            "SELECT so, tieu_de, nam, pdf_url FROM an_le_chinh_thuc WHERE so = ANY(%s)", (final,))}
        kq = []
        for k in final:
            m = meta.get(k, {}); sim = best.get(k, (None, None))
            kq.append({"so": k, "nam": m.get("nam"), "tieu_de": m.get("tieu_de"),
                       "do_tuong_dong": round(sim[0], 3) if sim[0] is not None else None,
                       "trich_doan": (sim[1][:300] if sim[1] else None), "pdf_url": m.get("pdf_url")})
        ghi_chu = "Án lệ; nội dung từ OCR/Word — đối chiếu PDF khi cần chính xác."
    else:  # dieu_luat
        fts = query(f"""SELECT a.article_anchor AS k,
                        ts_rank_cd({_RANK_W}, a.search_vector,
                        plainto_tsquery('simple', unaccent(%s))) AS diem
                        FROM articles a
                        WHERE a.search_vector @@ plainto_tsquery('simple', unaccent(%s))
                        ORDER BY diem DESC LIMIT 60""", (cau_hoi, cau_hoi))
        final = _rrf([(vec_order, 1.0), ([r["k"] for r in fts][:25], 0.5)])[:gioi_han]
        meta = {r["article_anchor"]: r for r in query(f"""
            SELECT a.article_anchor, a.ma_phap_dien, a.article_title, s.topic_title,
                   {SOURCE_URL} AS source_url
            FROM articles a LEFT JOIN subjects s ON s.subject_id = a.subject_id
            WHERE a.article_anchor = ANY(%s)""", (final,))}
        kq = []
        for k in final:
            m = meta.get(k, {}); sim = best.get(k, (None, None))
            kq.append({"ma_phap_dien": m.get("ma_phap_dien"), "tieu_de": m.get("article_title"),
                       "chu_de": m.get("topic_title"),
                       "do_tuong_dong": round(sim[0], 3) if sim[0] is not None else None,
                       "trich_doan": (sim[1][:300] if sim[1] else None), "source_url": m.get("source_url")})
        ghi_chu = "Điều luật thành văn; mở toàn văn bằng xem_dieu_luat(ma_phap_dien)."
    if not final:
        return {"tong_so": 0, "ket_qua": [], "goi_y": "Thử tra_luat/tra_an_le_ct với từ khóa cụ thể."}
    return {"tong_so": len(kq), "nguon": nguon, "phuong_phap": "hybrid vector+FTS (RRF)",
            "ket_qua": kq, "ghi_chu": ghi_chu}


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
    al = query("SELECT count(*) AS c FROM an_le_chinh_thuc")[0]["c"]
    return {"dieu_luat": dl, "chu_de": cd, "ban_an": ba, "an_le_chinh_thuc": al,
            "ghi_chu": "an_le_chinh_thuc = toàn văn 90 án lệ chính thức; ban_an = bản án minh họa."}


def main():
    """Entry point cho console script / uvx."""
    mcp.run()


if __name__ == "__main__":
    main()
