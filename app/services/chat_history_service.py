from __future__ import annotations

from typing import Any

from app.database.sql_server import get_sql_server_connection


class ChatHistoryService:
    @staticmethod
    def create_history(
        username_fk: str,
        question: str,
        response_content: str,
        response_format: str = "markdown",
        response_status: str = "success",
    ) -> int | None:
        clean_username = username_fk.strip()
        clean_question = question.strip()
        clean_response_content = response_content or ""
        clean_response_format = response_format.strip() or "markdown"
        clean_response_status = response_status.strip() or "success"

        if not clean_username:
            raise ValueError("username_fk is required.")

        if not clean_question:
            raise ValueError("question is required.")

        query = """
        INSERT INTO [sch_meettrack].[meetingsChatBotHistory]
        (
            [username_fk],
            [question],
            [response_content],
            [response_format],
            [response_status],
            [created_at],
            [updated_at]
        )
        OUTPUT INSERTED.[id_history]
        VALUES
        (
            ?,
            ?,
            ?,
            ?,
            ?,
            SYSDATETIME(),
            SYSDATETIME()
        );
        """

        connection = get_sql_server_connection()

        try:
            cursor = connection.cursor()

            cursor.execute(
                query,
                (
                    clean_username,
                    clean_question,
                    clean_response_content,
                    clean_response_format,
                    clean_response_status,
                ),
            )

            row = cursor.fetchone()
            connection.commit()

            if not row:
                return None

            return int(row[0])

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    @staticmethod
    def get_history_by_id(
        username_fk: str,
        id_history: int,
    ) -> dict[str, Any] | None:
        clean_username = username_fk.strip()

        if not clean_username:
            raise ValueError("username_fk is required.")

        query = """
        SELECT TOP 1
            [id_history],
            [question],
            [response_content],
            [response_format],
            [response_status],
            [created_at]
        FROM [sch_meettrack].[meetingsChatBotHistory]
        WHERE [username_fk] = ?
          AND [id_history] = ?
        ORDER BY [created_at] DESC;
        """

        connection = get_sql_server_connection()

        try:
            cursor = connection.cursor()
            cursor.execute(query, (clean_username, id_history))
            row = cursor.fetchone()

            if not row:
                return None

            return {
                "id_history": int(row[0]),
                "question": row[1] or "",
                "response_content": row[2] or "",
                "response_format": row[3] or "",
                "response_status": row[4] or "",
                "created_at": str(row[5]) if row[5] else "",
            }

        finally:
            connection.close()

    @staticmethod
    def get_recent_history(
        username_fk: str,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        clean_username = username_fk.strip()
        safe_limit = max(0, min(int(limit), 20))

        if not clean_username:
            raise ValueError("username_fk is required.")

        if safe_limit <= 0:
            return []

        query = """
        SELECT TOP (?)
            [id_history],
            [question],
            [response_content],
            [response_format],
            [response_status],
            [created_at]
        FROM [sch_meettrack].[meetingsChatBotHistory]
        WHERE [username_fk] = ?
        ORDER BY [created_at] DESC;
        """

        connection = get_sql_server_connection()

        try:
            cursor = connection.cursor()
            cursor.execute(query, (safe_limit, clean_username))
            rows = cursor.fetchall()

            items = [
                {
                    "id_history": int(row[0]),
                    "question": row[1] or "",
                    "response_content": row[2] or "",
                    "response_format": row[3] or "",
                    "response_status": row[4] or "",
                    "created_at": str(row[5]) if row[5] else "",
                }
                for row in rows
            ]

            return list(reversed(items))

        finally:
            connection.close()
