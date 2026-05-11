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
                "The 'data' property must be a list of meetings."
            )

        for meeting in meetings:
            documents.extend(
                DocumentBuilderService._build_documents_for_meeting(meeting)
            )

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
            activities
        )

        return f"""
Document type: Full meeting context

Main data:
- Meeting ID: {meeting_id}
- Meeting GUID: {meeting_guid}
- Title: {meeting_title}
- Subject: {meeting_subject}
- Description: {meeting_description}
- Status: {meeting_status}
- Location: {meeting_location}
- Series: {series_name}
- Organization: {org_name}
- Start: {start_date}
- End: {end_date}
- Normalized start date: {meeting_start_date}
- Normalized end date: {meeting_end_date}
- Meeting year-month: {meeting_year_month}

Structural summary:
- Total notes: {len(notes)}
- Total activities: {len(activities)}
- Critical notes: {len(critical_notes)}
- Action notes: {len(action_notes)}
- Open activities: {len(open_activities)}
- Closed activities: {len(closed_activities)}
- Activities with possible inconsistency: {len(inconsistent_activities)}

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
        lines = ["Highlight candidates for the summary:"]

        if critical_notes:
            lines.append("Critical notes detected:")
            for note in critical_notes:
                lines.append(
                    f"- Topic: {clean_text(note.get('topicName')) or 'General'} | "
                    f"Content: {clean_text(note.get('noteContent'))}"
                )

        if action_notes:
            lines.append("Action notes detected:")
            for note in action_notes:
                lines.append(
                    f"- Topic: {clean_text(note.get('topicName')) or 'General'} | "
                    f"Content: {clean_text(note.get('noteContent'))}"
                )

        if open_activities:
            lines.append("Open activities detected:")
            for activity in open_activities:
                lines.append(
                    f"- Owner: {clean_text(activity.get('assignedTo'))} | "
                    f"Topic: {clean_text(activity.get('topicName')) or 'General'} | "
                    f"Activity: {clean_text(activity.get('activityDescription'))} | "
                    f"Target date: {clean_text(activity.get('targetDate'))}"
                )

        if closed_activities:
            lines.append("Closed activities detected:")
            for activity in closed_activities:
                lines.append(
                    f"- Owner: {clean_text(activity.get('assignedTo'))} | "
                    f"Topic: {clean_text(activity.get('topicName')) or 'General'} | "
                    f"Activity: {clean_text(activity.get('activityDescription'))} | "
                    f"Closed date: {clean_text(activity.get('completedAt'))}"
                )

        if inconsistent_activities:
            lines.append("Inconsistencies detected:")
            for activity in inconsistent_activities:
                lines.append(
                    f"- The activity '{clean_text(activity.get('activityDescription'))}' "
                    f"appears as Open but has completedAt: {clean_text(activity.get('completedAt'))}"
                )

        if len(lines) == 1:
            lines.append(
                "There are no clear critical highlights, actions, or inconsistencies."
            )

        return "\n".join(lines)

    @staticmethod
    def _format_topics_section(
        notes_by_topic: dict[str, list[dict[str, Any]]],
        activities_by_topic: dict[str, list[dict[str, Any]]],
    ) -> str:
        topics = sorted(
            set(notes_by_topic.keys()) | set(activities_by_topic.keys())
        )

        if not topics:
            return "Detected topics:\nNo topics were detected."

        lines = ["Detected topics and context by topic:"]

        for topic in topics:
            notes_count = len(notes_by_topic.get(topic, []))
            activities_count = len(activities_by_topic.get(topic, []))

            lines.append(
                f"""
Topic: {topic}
- Related notes: {notes_count}
- Related activities: {activities_count}
""".strip()
            )

        return "\n\n".join(lines)

    @staticmethod
    def _format_notes_section(notes: list[dict[str, Any]]) -> str:
        if not notes:
            return "Registered notes:\nNo notes were registered."

        lines = ["Registered notes:"]

        for index, note in enumerate(notes, start=1):
            note_id = note.get("idNote")
            note_type = clean_text(note.get("noteType"))
            note_content = clean_text(note.get("noteContent"))
            topic_name = clean_text(note.get("topicName")) or "General"
            created_at = clean_text(note.get("createdAt"))
            note_created_date = normalize_date(created_at)

            lines.append(
                f"""
Note {index}:
- Note ID: {note_id}
- Type: {note_type}
- Topic: {topic_name}
- Created at: {created_at}
- Normalized date: {note_created_date}
- Content: {note_content}
""".strip()
            )

        return "\n\n".join(lines)

    @staticmethod
    def _format_activities_section(activities: list[dict[str, Any]]) -> str:
        if not activities:
            return "Registered activities:\nNo activities were registered."

        lines = ["Registered activities:"]

        for index, activity in enumerate(activities, start=1):
            activity_id = activity.get("idActivity")
            topic_name = clean_text(activity.get("topicName")) or "General"
            assigned_to = clean_text(activity.get("assignedTo"))
            activity_description = clean_text(
                activity.get("activityDescription")
            )
            activity_status = clean_text(activity.get("activityStatus"))
            target_date = clean_text(activity.get("targetDate"))
            completed_at = clean_text(activity.get("completedAt"))
            activity_target_date = normalize_date(target_date)
            activity_completed_date = normalize_date(completed_at)

            inconsistency = ""
            if activity_status.lower() == "open" and completed_at:
                inconsistency = "Yes, it appears as Open but has a closed date."

            lines.append(
                f"""
Activity {index}:
- Activity ID: {activity_id}
- Topic: {topic_name}
- Owner: {assigned_to}
- Status: {activity_status}
- Target date: {target_date}
- Normalized target date: {activity_target_date}
- Closed date: {completed_at}
- Normalized closed date: {activity_completed_date}
- Possible inconsistency: {inconsistency}
- Description: {activity_description}
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
Document type: Meeting note

Meeting context:
- Meeting ID: {meeting_id}
- Meeting title: {meeting_title}
- Meeting subject: {meeting_subject}
- Meeting status: {meeting_status}
- Location: {meeting_location}
- Series: {series_name}
- Organization: {org_name}
- Meeting date: {meeting_start_date}
- Meeting year-month: {meeting_year_month}

Note detail:
- Note ID: {note_id}
- Note type: {note_type}
- Topic: {topic_name}
- Topic ID: {topic_id}
- Creation date: {created_at}
- Normalized creation date: {note_created_date}

Content:
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
            inconsistency = "The activity appears as Open but has completedAt."

        activity_text = f"""
Document type: Meeting activity

Meeting context:
- Meeting ID: {meeting_id}
- Meeting title: {meeting_title}
- Meeting subject: {meeting_subject}
- Meeting status: {meeting_status}
- Location: {meeting_location}
- Series: {series_name}
- Organization: {org_name}
- Meeting date: {meeting_start_date}
- Meeting year-month: {meeting_year_month}

Activity detail:
- Activity ID: {activity_id}
- Topic: {topic_name}
- Topic ID: {topic_id}
- Owner: {assigned_to}
- Activity status: {activity_status}
- Target date: {target_date}
- Normalized target date: {activity_target_date}
- Closed date: {completed_at}
- Normalized closed date: {activity_completed_date}
- Possible inconsistency: {inconsistency}

Description:
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
