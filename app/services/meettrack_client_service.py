from __future__ import annotations

import requests
import urllib3

from app.utils.settings import get_settings


class MeetTrackClientService:
    @staticmethod
    def fetch_train_data() -> dict:
        settings = get_settings()

        if not settings.meettrack_verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        headers = {
            "X-AI-Token": settings.meettrack_x_ai_token,
            "Content-Type": "application/json",
        }

        method = settings.meettrack_http_method.upper().strip()

        try:
            if method == "POST":
                response = requests.post(
                    settings.meettrack_train_data_url,
                    headers=headers,
                    json={},
                    timeout=settings.meettrack_timeout_seconds,
                    verify=settings.meettrack_verify_ssl,
                )
            else:
                response = requests.get(
                    settings.meettrack_train_data_url,
                    headers=headers,
                    timeout=settings.meettrack_timeout_seconds,
                    verify=settings.meettrack_verify_ssl,
                )

            response.raise_for_status()

        except requests.exceptions.SSLError as error:
            raise RuntimeError(
                "MeetTrack SSL error. Check the corporate certificate or temporarily use MEETTRACK_VERIFY_SSL=false."
            ) from error

        except requests.exceptions.ConnectTimeout as error:
            raise RuntimeError(
                "MeetTrack connection timeout. Could not connect to the endpoint."
            ) from error

        except requests.exceptions.ReadTimeout as error:
            raise RuntimeError(
                "MeetTrack read timeout. The endpoint took too long to respond."
            ) from error

        except requests.exceptions.ConnectionError as error:
            raise RuntimeError(
                "MeetTrack connection error. Check VPN, Bosch internal network, proxy, or URL."
            ) from error

        except requests.exceptions.HTTPError as error:
            status_code = error.response.status_code if error.response else "unknown"
            detail = error.response.text if error.response else str(error)

            raise RuntimeError(
                f"MeetTrack HTTP error {status_code}: {detail}"
            ) from error

        data = response.json()

        if isinstance(data, list):
            return {
                "totalRecords": len(data),
                "data": data,
            }

        if not isinstance(data, dict):
            raise ValueError("The endpoint response is not valid JSON.")

        if "data" not in data:
            raise ValueError(
                "The endpoint response does not contain the 'data' property."
            )

        if "totalRecords" not in data:
            data["totalRecords"] = len(data.get("data", []))

        return data

    @staticmethod
    def test_connection() -> dict:
        try:
            data = MeetTrackClientService.fetch_train_data()

            return {
                "status": "ok",
                "totalRecords": data.get("totalRecords", 0),
                "has_data": isinstance(data.get("data"), list),
            }

        except Exception as error:
            return {
                "status": "error",
                "error_type": type(error).__name__,
                "error": str(error),
            }
