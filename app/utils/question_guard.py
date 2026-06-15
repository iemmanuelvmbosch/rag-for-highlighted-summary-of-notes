from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.utils.text_utils import clean_text, normalize_label, normalize_year_month


QuestionIntent = Literal[
    "rag",
    "conversation_followup",
    "out_of_scope",
]


@dataclass
class QuestionGuardResult:
    intent: QuestionIntent
    reason: str
    use_chroma: bool
    use_conversation_context: bool


DOMAIN_KEYWORDS = {
    "meettrack",
    "reunion",
    "reuniones",
    "junta",
    "juntas",
    "meeting",
    "meetings",
    "nota",
    "notas",
    "note",
    "notes",
    "actividad",
    "actividades",
    "activity",
    "activities",
    "highlight",
    "highlights",
    "topico",
    "topicos",
    "tema",
    "temas",
    "responsable",
    "responsables",
    "owner",
    "assigned",
    "asignado",
    "asignada",
    "asignadas",
    "pendiente",
    "pendientes",
    "abierta",
    "abiertas",
    "abierto",
    "abiertos",
    "cerrada",
    "cerradas",
    "cerrado",
    "cerrados",
    "accion",
    "acciones",
    "critica",
    "criticas",
    "critico",
    "criticos",
    "inconsistencia",
    "inconsistencias",
    "completedat",
    "targetdate",
    "fecha objetivo",
    "fecha de cierre",
    "cierre",
    "cierres",
    "resumen ejecutivo",
    "minuta",
    "seguimiento",
    "riesgo",
    "riesgos",
    "bloqueo",
    "bloqueos",
}


TEMPORAL_RAG_PATTERNS = [
    r"\bque paso\b",
    r"\bque sucedio\b",
    r"\bque ocurrio\b",
    r"\bresumen del dia\b",
    r"\bresumen de dia\b",
    r"\bresumen del mes\b",
    r"\bresumen mensual\b",
    r"\bdame el resumen\b",
    r"\bque hubo\b",
]


FOLLOWUP_PATTERNS = [
    r"\beso\b",
    r"\bese mensaje\b",
    r"\beste mensaje\b",
    r"\bla respuesta anterior\b",
    r"\blo anterior\b",
    r"\bel punto anterior\b",
    r"\blo que dijiste\b",
    r"\bmencionaste\b",
    r"\bexplicame mejor\b",
    r"\bdame mas detalle\b",
    r"\bmas detalle\b",
    r"\bhazlo\b",
    r"\bconviertelo\b",
    r"\bresumelo\b",
    r"\breescribelo\b",
    r"\bhazlo mas ejecutivo\b",
    r"\bhazlo mas corto\b",
    r"\ben una tabla\b",
    r"\ben bullets\b",
    r"\ben viñetas\b",
]


OUT_OF_SCOPE_PATTERNS = [
    r"\bcuanto es\b",
    r"\bcuánto es\b",
    r"\bcalcula\b",
    r"\bcalcular\b",
    r"\bsuma\b",
    r"\bresta\b",
    r"\bmultiplica\b",
    r"\bdivide\b",
    r"\btraduce\b",
    r"\btraducir\b",
    r"\bcapital de\b",
    r"\bquien es\b",
    r"\bquién es\b",
    r"\bclima\b",
    r"\btemperatura\b",
    r"\bprograma\b",
    r"\bcodigo\b",
    r"\bcódigo\b",
]


def _has_domain_keyword(normalized_question: str) -> bool:
    return any(keyword in normalized_question for keyword in DOMAIN_KEYWORDS)


def _matches_any_pattern(normalized_question: str, patterns: list[str]) -> bool:
    return any(
        re.search(pattern, normalized_question, flags=re.IGNORECASE)
        for pattern in patterns
    )


def _looks_like_math_question(normalized_question: str) -> bool:
    text = normalized_question.strip()

    if _matches_any_pattern(text, OUT_OF_SCOPE_PATTERNS):
        return True

    if re.search(r"\b\d+\s*(x|\*|por|\+|\-|/|entre)\s*\d+\b", text):
        return True

    if re.fullmatch(r"[\d\s\+\-\*/xX\.\(\)]+", text):
        return True

    return False


def _has_explicit_date_or_month(question: str) -> bool:
    text = clean_text(question)

    if re.search(r"\b20\d{2}-\d{1,2}-\d{1,2}\b", text):
        return True

    if re.search(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b", text):
        return True

    if normalize_year_month(text):
        return True

    normalized = normalize_label(text)

    relative_terms = [
        "hoy",
        "ayer",
        "manana",
        "mañana",
        "este mes",
        "mes actual",
        "mes pasado",
    ]

    return any(term in normalized for term in relative_terms)


def classify_question(
    question: str,
    has_conversation_context: bool = False,
    has_explicit_date_filter: bool = False,
    has_explicit_year_month_filter: bool = False,
    mode: str = "auto",
) -> QuestionGuardResult:
    raw_question = clean_text(question)
    normalized_question = normalize_label(raw_question)

    if not normalized_question:
        return QuestionGuardResult(
            intent="out_of_scope",
            reason="empty_question",
            use_chroma=False,
            use_conversation_context=False,
        )

    has_domain = _has_domain_keyword(normalized_question)
    has_temporal_rag_pattern = _matches_any_pattern(
        normalized_question,
        TEMPORAL_RAG_PATTERNS,
    )
    has_followup = _matches_any_pattern(
        normalized_question,
        FOLLOWUP_PATTERNS,
    )
    has_date_or_month = (
        has_explicit_date_filter
        or has_explicit_year_month_filter
        or _has_explicit_date_or_month(raw_question)
    )

    if _looks_like_math_question(normalized_question) and not has_domain:
        return QuestionGuardResult(
            intent="out_of_scope",
            reason="math_or_general_question",
            use_chroma=False,
            use_conversation_context=False,
        )

    if has_followup and has_conversation_context:
        return QuestionGuardResult(
            intent="conversation_followup",
            reason="followup_with_context",
            use_chroma=has_domain or has_temporal_rag_pattern or has_date_or_month,
            use_conversation_context=True,
        )

    if mode in ("day", "month") and has_date_or_month:
        return QuestionGuardResult(
            intent="rag",
            reason="forced_temporal_rag_mode",
            use_chroma=True,
            use_conversation_context=False,
        )

    if has_domain or has_temporal_rag_pattern or has_date_or_month:
        return QuestionGuardResult(
            intent="rag",
            reason="rag_domain_question",
            use_chroma=True,
            use_conversation_context=False,
        )

    return QuestionGuardResult(
        intent="out_of_scope",
        reason="not_related_to_meettrack",
        use_chroma=False,
        use_conversation_context=False,
    )


def build_out_of_scope_answer() -> str:
    return (
        "Solo puedo responder preguntas relacionadas con MeetTrack: "
        "reuniones, notas, actividades, highlights, responsables, fechas objetivo, "
        "fechas de cierre e inconsistencias. "
        "Intenta preguntarme algo como: **“¿Qué actividades abiertas hay?”** "
        "o **“¿Qué pasó en febrero 2026?”**"
    )
