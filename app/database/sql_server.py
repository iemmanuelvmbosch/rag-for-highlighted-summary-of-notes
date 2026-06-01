from __future__ import annotations

import pyodbc

from app.utils.settings import get_settings


def _required(value: str | None, env_name: str) -> str:
    if value is None or not str(value).strip():
        raise RuntimeError(f"{env_name} is required in the .env file.")

    return str(value).strip()


def get_sql_server_connection() -> pyodbc.Connection:
    settings = get_settings()

    driver = _required(settings.db_odbc_driver, "DB_ODBC_DRIVER")
    server = _required(settings.db_server, "DB_SERVER")
    database = _required(settings.db_name, "DB_NAME")
    username = _required(settings.db_user, "DB_USER")
    password = _required(settings.db_password, "DB_PASSWORD")

    connection_string = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        f"Encrypt={settings.db_encrypt};"
        f"TrustServerCertificate={settings.db_trust_server_certificate};"
        f"Connection Timeout={settings.db_connection_timeout};"
    )

    return pyodbc.connect(connection_string)


def test_sql_server_connection() -> dict:
    try:
        connection = get_sql_server_connection()

        try:
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            row = cursor.fetchone()

            return {
                "status": "ok",
                "result": int(row[0]) if row else None,
            }

        finally:
            connection.close()

    except Exception as error:
        return {
            "status": "error",
            "error_type": type(error).__name__,
            "error": str(error),
        }
