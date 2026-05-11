from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.models.rag_models import RagDocument
from app.utils.text_utils import (
    build_metadata,
    calculate_text_hash,
    clean_text,
    collection_key_from_date,
    normalize_date,
    year_month_from_date,
)


class DocumentBuilderService:
    @staticmethod
    def build_documents(api_response: dict) -> list[RagDocument]:
        meetings = api_response.get("data", [])
        documents: list[RagDocument] = []

        if not isinstance(meetings, list):
            raise ValueError(
                "La propiedad 'data' debe ser una lista de reuniones.")

        for meeting in meetings:
            documents.extend(
                DocumentBuilderService._build_documents_for_meeting(meeting))

        return documents

    @staticmethod
    def _build_documents_for_meeting(meeting: dict[str, Any]) -> list[RagDocument]:
        documents: list[RagDocument] = []

        meeting_id = meeting.get("idMeeting")
        meeting_title = clean_text(meeting.get("meetingTitle"))
        meeting_description = clean_text(meeting.get("meetingDescription"))
        meeting_subject = clean_text(meeting.get("meetingSubject"))
        meeting_status = clean_text(meeting.get("meetingStatus"))
        meeting_location = clean_text(meeting.get("meetingLocation"))
        series_name = clean_text(meeting.get("seriesName"))
        org_name = clean_text(meeting.get("orgName"))
        meeting_guid = clean_text(meeting.get("meetingGuid"))
        start_date = clean_text(meeting.get("startDate"))
        end_date = clean_text(meeting.get("endDate"))

        meeting_start_date = normalize_date(start_date)
        meeting_end_date = normalize_date(end_date)
        meeting_year_month = year_month_from_date(start_date)
        collection_key = collection_key_from_date(start_date)

        notes = meeting.get("notes") or []
        activities = meeting.get("activities") or []

        notes_by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
        activities_by_topic: dict[str,
                                  list[dict[str, Any]]] = defaultdict(list)

        for note in notes:
            topic_name = clean_text(note.get("topicName")) or "General"
            notes_by_topic[topic_name].append(note)

        for activity in activities:
            topic_name = clean_text(activity.get("topicName")) or "General"
            activities_by_topic[topic_name].append(activity)

        full_context_text = DocumentBuilderService._build_full_meeting_context_text(
            meeting_id=meeting_id,
            meeting_guid=meeting_guid,
            meeting_title=meeting_title,
            meeting_description=meeting_description,
            meeting_subject=meeting_subject,
            meeting_status=meeting_status,
            meeting_location=meeting_location,
            series_name=series_name,
            org_name=org_name,
            start_date=start_date,
            end_date=end_date,
            meeting_start_date=meeting_start_date,
            meeting_end_date=meeting_end_date,
            meeting_year_month=meeting_year_month,
            notes=notes,
            activities=activities,
            notes_by_topic=notes_by_topic,
            activities_by_topic=activities_by_topic,
        )

        documents.append(
            RagDocument(
                id=f"meeting_{meeting_id}_full_context",
                text=full_context_text,
                metadata=build_metadata(
                    {
                        "collection_key": collection_key,
                        "document_type": "meeting_full_context",
                        "meeting_id": meeting_id,
                        "meeting_guid": meeting_guid,
                        "meeting_title": meeting_title,
                        "meeting_subject": meeting_subject,
                        "meeting_status": meeting_status,
                        "meeting_location": meeting_location,
                        "series_name": series_name,
                        "org_name": org_name,
                        "start_date": start_date,
                        "end_date": end_date,
                        "meeting_start_date": meeting_start_date,
                        "meeting_end_date": meeting_end_date,
                        "meeting_year_month": meeting_year_month,
                        "notes_count": len(notes),
                        "activities_count": len(activities),
                        "content_hash": calculate_text_hash(full_context_text),
                    }
                ),
            )
        )

        for note in notes:
            documents.append(
                DocumentBuilderService._build_note_document(
                    note=note,
                    meeting_id=meeting_id,
                    meeting_guid=meeting_guid,
                    meeting_title=meeting_title,
                    meeting_subject=meeting_subject,
                    meeting_status=meeting_status,
                    meeting_location=meeting_location,
                    series_name=series_name,
                    org_name=org_name,
                    meeting_start_date=meeting_start_date,
                    meeting_end_date=meeting_end_date,
                    meeting_year_month=meeting_year_month,
                    collection_key=collection_key,
                )
            )

        for activity in activities:
            documents.append(
                DocumentBuilderService._build_activity_document(
                    activity=activity,
                    meeting_id=meeting_id,
                    meeting_guid=meeting_guid,
                    meeting_title=meeting_title,
                    meeting_subject=meeting_subject,
                    meeting_status=meeting_status,
                    meeting_location=meeting_location,
                    series_name=series_name,
                    org_name=org_name,
                    meeting_start_date=meeting_start_date,
                    meeting_end_date=meeting_end_date,
                    meeting_year_month=meeting_year_month,
                    collection_key=collection_key,
                )
            )

        return documents

    @staticmethod
    def _build_full_meeting_context_text(
        meeting_id: Any,
        meeting_guid: str,
        meeting_title: str,
        meeting_description: str,
        meeting_subject: str,
        meeting_status: str,
        meeting_location: str,
        series_name: str,
        org_name: str,
        start_date: str,
        end_date: str,
        meeting_start_date: str,
        meeting_end_date: str,
        meeting_year_month: str,
        notes: list[dict[str, Any]],
        activities: list[dict[str, Any]],
        notes_by_topic: dict[str, list[dict[str, Any]]],
        activities_by_topic: dict[str, list[dict[str, Any]]],
    ) -> str:
        critical_notes = [
            note for note in notes if clean_text(note.get("noteType")).lower() == "critica"
        ]

        action_notes = [
            note for note in notes if clean_text(note.get("noteType")).lower() == "accion"
        ]

        open_activities = [
            activity
            for activity in activities
            if clean_text(activity.get("activityStatus")).lower() == "open"
        ]

        closed_activities = [
            activity
            for activity in activities
            if clean_text(activity.get("activityStatus")).lower() == "closed"
        ]

        inconsistent_activities = [
            activity
            for activity in activities
            if clean_text(activity.get("activityStatus")).lower() == "open"
            and clean_text(activity.get("completedAt"))
        ]

        highlights_section = DocumentBuilderService._format_highlights_candidates_section(
            critical_notes=critical_notes,
            action_notes=action_notes,
            open_activities=open_activities,
            closed_activities=closed_activities,
            inconsistent_activities=inconsistent_activities,
        )

        topics_section = DocumentBuilderService._format_topics_section(
            notes_by_topic=notes_by_topic,
            activities_by_topic=activities_by_topic,
        )

        notes_section = DocumentBuilderService._format_notes_section(notes)
        activities_section = DocumentBuilderService._format_activities_section(
            activities)

        return f"""
Tipo de documento: Contexto completo de reunión

Datos principales:
- ID de reunión: {meeting_id}
- GUID de reunión: {meeting_guid}
- Título: {meeting_title}
- Asunto: {meeting_subject}
- Descripción: {meeting_description}
- Estado: {meeting_status}
- Ubicación: {meeting_location}
- Serie: {series_name}
- Organización: {org_name}
- Inicio: {start_date}
- Fin: {end_date}
- Fecha normalizada de inicio: {meeting_start_date}
- Fecha normalizada de fin: {meeting_end_date}
- Mes-año de la reunión: {meeting_year_month}

Resumen estructural:
- Total de notas: {len(notes)}
- Total de actividades: {len(activities)}
- Notas críticas: {len(critical_notes)}
- Notas de acción: {len(action_notes)}
- Actividades abiertas: {len(open_activities)}
- Actividades cerradas: {len(closed_activities)}
- Actividades con posible inconsistencia: {len(inconsistent_activities)}

{highlights_section}

{topics_section}

{notes_section}

{activities_section}
""".strip()

    @staticmethod
    def _format_highlights_candidates_section(
        critical_notes: list[dict[str, Any]],
        action_notes: list[dict[str, Any]],
        open_activities: list[dict[str, Any]],
        closed_activities: list[dict[str, Any]],
        inconsistent_activities: list[dict[str, Any]],
    ) -> str:
        lines = ["Highlights candidatos para el resumen:"]

        if critical_notes:
            lines.append("Notas críticas detectadas:")
            for note in critical_notes:
                lines.append(
                    f"- Tópico: {clean_text(note.get('topicName')) or 'General'} | "
                    f"Contenido: {clean_text(note.get('noteContent'))}"
                )

        if action_notes:
            lines.append("Notas de acción detectadas:")
            for note in action_notes:
                lines.append(
                    f"- Tópico: {clean_text(note.get('topicName')) or 'General'} | "
                    f"Contenido: {clean_text(note.get('noteContent'))}"
                )

        if open_activities:
            lines.append("Actividades abiertas detectadas:")
            for activity in open_activities:
                lines.append(
                    f"- Responsable: {clean_text(activity.get('assignedTo'))} | "
                    f"Tópico: {clean_text(activity.get('topicName')) or 'General'} | "
                    f"Actividad: {clean_text(activity.get('activityDescription'))} | "
                    f"Fecha objetivo: {clean_text(activity.get('targetDate'))}"
                )

        if closed_activities:
            lines.append("Actividades cerradas detectadas:")
            for activity in closed_activities:
                lines.append(
                    f"- Responsable: {clean_text(activity.get('assignedTo'))} | "
                    f"Tópico: {clean_text(activity.get('topicName')) or 'General'} | "
                    f"Actividad: {clean_text(activity.get('activityDescription'))} | "
                    f"Fecha de cierre: {clean_text(activity.get('completedAt'))}"
                )

        if inconsistent_activities:
            lines.append("Inconsistencias detectadas:")
            for activity in inconsistent_activities:
                lines.append(
                    f"- La actividad '{clean_text(activity.get('activityDescription'))}' "
                    f"aparece como Open pero tiene completedAt: {clean_text(activity.get('completedAt'))}"
                )

        if len(lines) == 1:
            lines.append(
                "No hay highlights críticos, acciones o inconsistencias claras.")

        return "\n".join(lines)

    @staticmethod
    def _format_topics_section(
        notes_by_topic: dict[str, list[dict[str, Any]]],
        activities_by_topic: dict[str, list[dict[str, Any]]],
    ) -> str:
        topics = sorted(set(notes_by_topic.keys()) |
                        set(activities_by_topic.keys()))

        if not topics:
            return "Tópicos detectados:\nNo se detectaron tópicos."

        lines = ["Tópicos detectados y contexto por tópico:"]

        for topic in topics:
            notes_count = len(notes_by_topic.get(topic, []))
            activities_count = len(activities_by_topic.get(topic, []))

            lines.append(
                f"""
Tópico: {topic}
- Notas relacionadas: {notes_count}
- Actividades relacionadas: {activities_count}
""".strip()
            )

        return "\n\n".join(lines)

    @staticmethod
    def _format_notes_section(notes: list[dict[str, Any]]) -> str:
        if not notes:
            return "Notas registradas:\nNo se registraron notas."

        lines = ["Notas registradas:"]

        for index, note in enumerate(notes, start=1):
            note_id = note.get("idNote")
            note_type = clean_text(note.get("noteType"))
            note_content = clean_text(note.get("noteContent"))
            topic_name = clean_text(note.get("topicName")) or "General"
            created_at = clean_text(note.get("createdAt"))
            note_created_date = normalize_date(created_at)

            lines.append(
                f"""
Nota {index}:
- ID de nota: {note_id}
- Tipo: {note_type}
- Tópico: {topic_name}
- Creada en: {created_at}
- Fecha normalizada: {note_created_date}
- Contenido: {note_content}
""".strip()
            )

        return "\n\n".join(lines)

    @staticmethod
    def _format_activities_section(activities: list[dict[str, Any]]) -> str:
        if not activities:
            return "Actividades registradas:\nNo se registraron actividades."

        lines = ["Actividades registradas:"]

        for index, activity in enumerate(activities, start=1):
            activity_id = activity.get("idActivity")
            topic_name = clean_text(activity.get("topicName")) or "General"
            assigned_to = clean_text(activity.get("assignedTo"))
            activity_description = clean_text(
                activity.get("activityDescription"))
            activity_status = clean_text(activity.get("activityStatus"))
            target_date = clean_text(activity.get("targetDate"))
            completed_at = clean_text(activity.get("completedAt"))
            activity_target_date = normalize_date(target_date)
            activity_completed_date = normalize_date(completed_at)

            inconsistency = ""
            if activity_status.lower() == "open" and completed_at:
                inconsistency = "Sí, aparece como Open pero tiene fecha de cierre."

            lines.append(
                f"""
Actividad {index}:
- ID de actividad: {activity_id}
- Tópico: {topic_name}
- Responsable: {assigned_to}
- Estado: {activity_status}
- Fecha objetivo: {target_date}
- Fecha objetivo normalizada: {activity_target_date}
- Fecha de cierre: {completed_at}
- Fecha de cierre normalizada: {activity_completed_date}
- Posible inconsistencia: {inconsistency}
- Descripción: {activity_description}
""".strip()
            )

        return "\n\n".join(lines)

    @staticmethod
    def _build_note_document(
        note: dict[str, Any],
        meeting_id: Any,
        meeting_guid: str,
        meeting_title: str,
        meeting_subject: str,
        meeting_status: str,
        meeting_location: str,
        series_name: str,
        org_name: str,
        meeting_start_date: str,
        meeting_end_date: str,
        meeting_year_month: str,
        collection_key: str,
    ) -> RagDocument:
        note_id = note.get("idNote")
        note_type = clean_text(note.get("noteType"))
        note_content = clean_text(note.get("noteContent"))
        topic_name = clean_text(note.get("topicName")) or "General"
        created_at = clean_text(note.get("createdAt"))
        note_created_date = normalize_date(created_at)
        topic_id = note.get("idTopicFk")

        note_text = f"""
Tipo de documento: Nota de reunión

Contexto de reunión:
- ID de reunión: {meeting_id}
- Título de reunión: {meeting_title}
- Asunto de reunión: {meeting_subject}
- Estado de reunión: {meeting_status}
- Ubicación: {meeting_location}
- Serie: {series_name}
- Organización: {org_name}
- Fecha de reunión: {meeting_start_date}
- Mes-año de reunión: {meeting_year_month}

Detalle de nota:
- ID de nota: {note_id}
- Tipo de nota: {note_type}
- Tópico: {topic_name}
- ID de tópico: {topic_id}
- Fecha de creación: {created_at}
- Fecha normalizada de creación: {note_created_date}

Contenido:
{note_content}
""".strip()

        return RagDocument(
            id=f"meeting_{meeting_id}_note_{note_id}",
            text=note_text,
            metadata=build_metadata(
                {
                    "collection_key": collection_key,
                    "document_type": "note",
                    "meeting_id": meeting_id,
                    "meeting_guid": meeting_guid,
                    "meeting_title": meeting_title,
                    "meeting_subject": meeting_subject,
                    "meeting_status": meeting_status,
                    "meeting_location": meeting_location,
                    "series_name": series_name,
                    "org_name": org_name,
                    "meeting_start_date": meeting_start_date,
                    "meeting_end_date": meeting_end_date,
                    "meeting_year_month": meeting_year_month,
                    "note_id": note_id,
                    "note_type": note_type,
                    "topic_id": topic_id,
                    "topic_name": topic_name,
                    "created_at": created_at,
                    "note_created_date": note_created_date,
                    "content_hash": calculate_text_hash(note_text),
                }
            ),
        )

    @staticmethod
    def _build_activity_document(
        activity: dict[str, Any],
        meeting_id: Any,
        meeting_guid: str,
        meeting_title: str,
        meeting_subject: str,
        meeting_status: str,
        meeting_location: str,
        series_name: str,
        org_name: str,
        meeting_start_date: str,
        meeting_end_date: str,
        meeting_year_month: str,
        collection_key: str,
    ) -> RagDocument:
        activity_id = activity.get("idActivity")
        topic_id = activity.get("idTopicFk")
        topic_name = clean_text(activity.get("topicName")) or "General"
        assigned_to = clean_text(activity.get("assignedTo"))
        activity_description = clean_text(activity.get("activityDescription"))
        activity_status = clean_text(activity.get("activityStatus"))
        target_date = clean_text(activity.get("targetDate"))
        completed_at = clean_text(activity.get("completedAt"))
        activity_target_date = normalize_date(target_date)
        activity_completed_date = normalize_date(completed_at)

        inconsistency = ""
        if activity_status.lower() == "open" and completed_at:
            inconsistency = "La actividad aparece como Open pero tiene completedAt."

        activity_text = f"""
Tipo de documento: Actividad de reunión

Contexto de reunión:
- ID de reunión: {meeting_id}
- Título de reunión: {meeting_title}
- Asunto de reunión: {meeting_subject}
- Estado de reunión: {meeting_status}
- Ubicación: {meeting_location}
- Serie: {series_name}
- Organización: {org_name}
- Fecha de reunión: {meeting_start_date}
- Mes-año de reunión: {meeting_year_month}

Detalle de actividad:
- ID de actividad: {activity_id}
- Tópico: {topic_name}
- ID de tópico: {topic_id}
- Responsable: {assigned_to}
- Estado de actividad: {activity_status}
- Fecha objetivo: {target_date}
- Fecha objetivo normalizada: {activity_target_date}
- Fecha de cierre: {completed_at}
- Fecha de cierre normalizada: {activity_completed_date}
- Posible inconsistencia: {inconsistency}

Descripción:
{activity_description}
""".strip()

        return RagDocument(
            id=f"meeting_{meeting_id}_activity_{activity_id}",
            text=activity_text,
            metadata=build_metadata(
                {
                    "collection_key": collection_key,
                    "document_type": "activity",
                    "meeting_id": meeting_id,
                    "meeting_guid": meeting_guid,
                    "meeting_title": meeting_title,
                    "meeting_subject": meeting_subject,
                    "meeting_status": meeting_status,
                    "meeting_location": meeting_location,
                    "series_name": series_name,
                    "org_name": org_name,
                    "meeting_start_date": meeting_start_date,
                    "meeting_end_date": meeting_end_date,
                    "meeting_year_month": meeting_year_month,
                    "activity_id": activity_id,
                    "activity_status": activity_status,
                    "assigned_to": assigned_to,
                    "topic_id": topic_id,
                    "topic_name": topic_name,
                    "target_date": target_date,
                    "completed_at": completed_at,
                    "activity_target_date": activity_target_date,
                    "activity_completed_date": activity_completed_date,
                    "content_hash": calculate_text_hash(activity_text),
                }
            ),
        )
