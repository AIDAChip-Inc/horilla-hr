"""F2 — build a VEVENT (.ics) for an interview.

Stable UID from the InterviewSchedule PK so a reschedule updates the existing
calendar event rather than creating a duplicate in most clients. SEQUENCE stays
0 for MVP (incrementing it on reschedule is a noted follow-up); the stable UID
already prevents duplicate events in the common clients.
"""

from datetime import datetime, timedelta

from django.utils import timezone

try:  # icalendar is a pinned dependency (requirements.txt)
    from icalendar import Calendar, Event, vCalAddress, vText
except ImportError:  # pragma: no cover - surfaced loudly, never silently skipped
    Calendar = None

DEFAULT_DURATION = timedelta(minutes=45)


def _uid(interview) -> str:
    return f"interview-{interview.pk}@aidachip.com"


def build_ics(interview, *, organizer_email: str | None = None) -> bytes:
    """Return the .ics bytes for ``interview`` (METHOD:REQUEST)."""
    if Calendar is None:  # dependency missing -> fail loud
        raise RuntimeError("icalendar is required for interview ICS emails")

    start_naive = datetime.combine(interview.interview_date, interview.interview_time)
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(start_naive, tz)
    end = start + DEFAULT_DURATION

    cal = Calendar()
    cal.add("prodid", "-//AIDAChip//Recruitment//EN")
    cal.add("version", "2.0")
    cal.add("method", "REQUEST")

    event = Event()
    event.add("uid", _uid(interview))
    event.add("sequence", 0)
    event.add("dtstamp", timezone.now())
    event.add("dtstart", start)
    event.add("dtend", end)
    event.add("summary", f"Interview: {interview.candidate_id.name}")
    if interview.description:
        event.add("description", interview.description)
    if organizer_email:
        org = vCalAddress(f"MAILTO:{organizer_email}")
        org.params["cn"] = vText("AIDAChip Recruitment")
        event["organizer"] = org
    for interviewer in interview.employee_id.all():
        email = interviewer.get_mail()
        if not email:
            continue
        attendee = vCalAddress(f"MAILTO:{email}")
        attendee.params["ROLE"] = vText("REQ-PARTICIPANT")
        attendee.params["RSVP"] = vText("TRUE")
        event.add("attendee", attendee, encode=0)

    cal.add_component(event)
    return cal.to_ical()
