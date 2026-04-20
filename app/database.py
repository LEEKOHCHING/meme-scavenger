import pyodbc
from contextlib import contextmanager
from .config import settings

_CONN_STR = (
    f"DRIVER={{ODBC Driver {settings.mssql_driver} for SQL Server}};"
    f"SERVER={settings.mssql_server};"
    f"DATABASE={settings.mssql_database};"
    f"UID={settings.mssql_user};"
    f"PWD={settings.mssql_password};"
    f"Encrypt={settings.mssql_encrypt};"
)


@contextmanager
def get_db():
    conn = pyodbc.connect(_CONN_STR, timeout=10)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
