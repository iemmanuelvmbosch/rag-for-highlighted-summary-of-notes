from __future__ import annotations

import hashlib
import re
import unicodedata
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

import dateparser
from dateparser.search import search_dates


MONTHS_ES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


@dataclass
class TemporalFilter:
    period: Literal["none", "day", "month"]
    date: str = ""
    year_month: str = ""
    collection_key: str = ""


@dataclass
class DateRangeFilter:
    filter_applied: bool
    start_date: str = ""
    end_date: str = ""
    year_month: str = ""
    source: str = "none"


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def normalize_label(value: Any) -> str:
    text = clean_text(value).lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(
        char for char in text
        if unicodedata.category(char) != "Mn"
    )
    return text.strip()


def fix_common_spanish_date_typos(text: str) -> str:
    text = clean_text(text)

    replacements = {
        "ferbrero": "febrero",
        "febreo": "febrero",
        "ferebro": "febrero",
        "febrerro": "febrero",
        "eneor": "enero",
        "marso": "marzo",
        "junoi": "junio",
        "juloi": "julio",
        "agusto": "agosto",
        "septimbre": "septiembre",
        "setimbre": "septiembre",
        "octuvre": "octubre",
        "novimbre": "noviembre",
        "diciimbre": "diciembre",
    }

    for wrong, right in replacements.items():
        text = re.sub(rf"\b{wrong}\b", right, text, flags=re.IGNORECASE)

    return text


def normalize_date(value: Any) -> str:
    text = clean_text(value)

    if not text:
        return ""

    text = fix_common_spanish_date_typos(text)

    try:
        iso_text = text.replace("Z", "")
        parsed = datetime.fromisoformat(iso_text)
        return parsed.date().isoformat()
    except Exception:
        pass

    parsed_date = dateparser.parse(
        text,
        languages=["es", "en"],
        settings={
            "DATE_ORDER": "DMY",
            "PREFER_DAY_OF_MONTH": "first",
        },
    )

    if not parsed_date:
        return ""

    return parsed_date.date().isoformat()


def normalize_year_month(value: Any) -> str:
    text = clean_text(value)

    if not text:
        return ""

    text = fix_common_spanish_date_typos(text).lower()

    iso_match = re.search(r"\b(20\d{2})[-/](0?[1-9]|1[0-2])\b", text)
    if iso_match:
        year = int(iso_match.group(1))
        month = int(iso_match.group(2))
        return f"{year:04d}-{month:02d}"

    slash_match = re.search(r"\b(0?[1-9]|1[0-2])[-/](20\d{2})\b", text)
    if slash_match:
        month = int(slash_match.group(1))
        year = int(slash_match.group(2))
        return f"{year:04d}-{month:02d}"

    month_names = "|".join(MONTHS_ES.keys())

    month_year_match = re.search(
        rf"\b({month_names})\b\s*(?:de\s*)?(20\d{{2}})",
        text,
        flags=re.IGNORECASE,
    )

    if month_year_match:
        month_name = month_year_match.group(1).lower()
        year = int(month_year_match.group(2))
        month = MONTHS_ES[month_name]
        return f"{year:04d}-{month:02d}"

    year_month_match = re.search(
        rf"\b(20\d{{2}})\b\s*(?:de\s*)?\b({month_names})\b",
        text,
        flags=re.IGNORECASE,
    )

    if year_month_match:
        year = int(year_month_match.group(1))
        month_name = year_month_match.group(2).lower()
        month = MONTHS_ES[month_name]
        return f"{year:04d}-{month:02d}"

    return ""


def year_month_from_date(date_value: Any) -> str:
    normalized = normalize_date(date_value)

    if not normalized:
        return ""

    return normalized[:7]


def collection_key_from_year_month(year_month: str) -> str:
    year_month = clean_text(year_month)

    if not re.fullmatch(r"\d{4}-\d{2}", year_month):
        return "unknown"

    return year_month.replace("-", "_")


def collection_key_from_date(date_value: Any) -> str:
    year_month = year_month_from_date(date_value)

    if not year_month:
        return "unknown"

    return collection_key_from_year_month(year_month)


def month_date_range(year_month: str) -> tuple[str, str]:
    normalized_year_month = normalize_year_month(year_month)

    if not normalized_year_month:
        return "", ""

    year = int(normalized_year_month[:4])
    month = int(normalized_year_month[5:7])
    last_day = monthrange(year, month)[1]

    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"


def text_has_explicit_day(text: str) -> bool:
    text = fix_common_spanish_date_typos(text).lower()

    if re.search(r"\b20\d{2}-\d{1,2}-\d{1,2}\b", text):
        return True

    if re.search(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b", text):
        return True

    month_names = "|".join(MONTHS_ES.keys())

    if re.search(
        rf"\b\d{{1,2}}\s*(?:de\s*)?\b({month_names})\b\s*(?:de\s*)?\b20\d{{2}}\b",
        text,
        flags=re.IGNORECASE,
    ):
        return True

    return False


def extract_date_from_question(question: str) -> str:
    text = clean_text(question)

    if not text:
        return ""

    text = fix_common_spanish_date_typos(text)

    found_dates = search_dates(
        text,
        languages=["es", "en"],
        settings={
            "DATE_ORDER": "DMY",
            "PREFER_DAY_OF_MONTH": "first",
        },
    )

    if not found_dates:
        return ""

    return found_dates[0][1].date().isoformat()


def _current_date() -> date:
    return datetime.now().date()


def extract_relative_temporal_filter(question: str) -> TemporalFilter:
    text = normalize_label(question)

    if not text:
        return TemporalFilter(period="none")

    today = _current_date()

    if re.search(r"\bhoy\b", text):
        value = today.isoformat()
        year_month = value[:7]
        return TemporalFilter(
            period="day",
            date=value,
            year_month=year_month,
            collection_key=collection_key_from_year_month(year_month),
        )

    if re.search(r"\bayer\b", text):
        value = (today - timedelta(days=1)).isoformat()
        year_month = value[:7]
        return TemporalFilter(
            period="day",
            date=value,
            year_month=year_month,
            collection_key=collection_key_from_year_month(year_month),
        )

    if re.search(r"\bmanana\b", text):
        value = (today + timedelta(days=1)).isoformat()
        year_month = value[:7]
        return TemporalFilter(
            period="day",
            date=value,
            year_month=year_month,
            collection_key=collection_key_from_year_month(year_month),
        )

    if "mes pasado" in text:
        first_day_current_month = today.replace(day=1)
        previous_month_day = first_day_current_month - timedelta(days=1)
        year_month = f"{previous_month_day.year:04d}-{previous_month_day.month:02d}"

        return TemporalFilter(
            period="month",
            year_month=year_month,
            collection_key=collection_key_from_year_month(year_month),
        )

    if (
        "este mes" in text
        or "mes actual" in text
        or "del mes" in text
        and "pasado" not in text
    ):
        year_month = f"{today.year:04d}-{today.month:02d}"

        return TemporalFilter(
            period="month",
            year_month=year_month,
            collection_key=collection_key_from_year_month(year_month),
        )

    return TemporalFilter(period="none")


def extract_temporal_filter(
    question: str,
    explicit_date: str | None = None,
    explicit_year_month: str | None = None,
) -> TemporalFilter:
    if explicit_date:
        normalized_date = normalize_date(explicit_date)

        if normalized_date:
            year_month = year_month_from_date(normalized_date)

            return TemporalFilter(
                period="day",
                date=normalized_date,
                year_month=year_month,
                collection_key=collection_key_from_year_month(year_month),
            )

    if explicit_year_month:
        normalized_year_month = normalize_year_month(explicit_year_month)

        if normalized_year_month:
            return TemporalFilter(
                period="month",
                year_month=normalized_year_month,
                collection_key=collection_key_from_year_month(
                    normalized_year_month
                ),
            )

    text = clean_text(question)

    if not text:
        return TemporalFilter(period="none")

    relative_filter = extract_relative_temporal_filter(text)
    if relative_filter.period != "none":
        return relative_filter

    if text_has_explicit_day(text):
        normalized_date = extract_date_from_question(text)

        if normalized_date:
            year_month = year_month_from_date(normalized_date)

            return TemporalFilter(
                period="day",
                date=normalized_date,
                year_month=year_month,
                collection_key=collection_key_from_year_month(year_month),
            )

    normalized_year_month = normalize_year_month(text)

    if normalized_year_month:
        return TemporalFilter(
            period="month",
            year_month=normalized_year_month,
            collection_key=collection_key_from_year_month(
                normalized_year_month
            ),
        )

    return TemporalFilter(period="none")


def build_date_range_filter(
    date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    year_month: str | None = None,
) -> DateRangeFilter:
    if date:
        normalized_date = normalize_date(date)

        if normalized_date:
            return DateRangeFilter(
                filter_applied=True,
                start_date=normalized_date,
                end_date=normalized_date,
                year_month=year_month_from_date(normalized_date),
                source="date",
            )

    if start_date or end_date:
        normalized_start = normalize_date(start_date) if start_date else ""
        normalized_end = normalize_date(end_date) if end_date else ""

        if normalized_start and not normalized_end:
            normalized_end = normalized_start

        if normalized_end and not normalized_start:
            normalized_start = normalized_end

        if normalized_start and normalized_end:
            if normalized_start > normalized_end:
                normalized_start, normalized_end = normalized_end, normalized_start

            return DateRangeFilter(
                filter_applied=True,
                start_date=normalized_start,
                end_date=normalized_end,
                year_month=year_month_from_date(normalized_start),
                source="range",
            )

    if year_month:
        normalized_year_month = normalize_year_month(year_month)

        if normalized_year_month:
            range_start, range_end = month_date_range(normalized_year_month)

            return DateRangeFilter(
                filter_applied=True,
                start_date=range_start,
                end_date=range_end,
                year_month=normalized_year_month,
                source="year_month",
            )

    return DateRangeFilter(filter_applied=False)


def is_date_in_range(date_value: Any, start_date: str, end_date: str) -> bool:
    normalized = normalize_date(date_value)

    if not normalized:
        return False

    return start_date <= normalized <= end_date


def meeting_matches_date_range(
    meeting: dict[str, Any],
    date_filter: DateRangeFilter,
    date_scope: Literal["meeting", "related"] = "meeting",
) -> bool:
    if not date_filter.filter_applied:
        return True

    start = date_filter.start_date
    end = date_filter.end_date

    meeting_dates = [
        meeting.get("startDate"),
        meeting.get("endDate"),
    ]

    if any(is_date_in_range(value, start, end) for value in meeting_dates):
        return True

    if date_scope == "meeting":
        return False

    notes = meeting.get("notes") or []
    activities = meeting.get("activities") or []

    for note in notes:
        if is_date_in_range(note.get("createdAt"), start, end):
            return True

    for activity in activities:
        if is_date_in_range(activity.get("targetDate"), start, end):
            return True

        if is_date_in_range(activity.get("completedAt"), start, end):
            return True

    return False


def calculate_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_metadata(value: Any) -> str | int | float | bool:
    if value is None:
        return ""

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def build_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    return {key: safe_metadata(value) for key, value in metadata.items()}
