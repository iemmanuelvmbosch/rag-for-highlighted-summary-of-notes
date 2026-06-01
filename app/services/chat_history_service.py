from __future__ import annotations

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
