"""Kết nối PostgreSQL (user chỉ-đọc). Cấu hình qua biến môi trường."""
import os
import psycopg2


def get_conn():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "127.0.0.1"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "appdb"),
        user=os.environ.get("PGUSER", "mcp_ro"),
        password=os.environ.get("PGPASSWORD", ""),
        connect_timeout=10,
    )


def query(sql, params=()):
    """Chạy SELECT, trả về list[dict]. Chỉ-đọc."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()
