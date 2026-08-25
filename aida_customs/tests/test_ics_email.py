"""F2 — interview scheduling emails a valid ICS invite.

Discriminates on the parsed attachment: DTSTART equals the exact scheduled
datetime and the interviewer is an attendee. Goes red if the date/time -> DTSTART
mapping breaks or the attachment is dropped (not existence-only).
"""

from datetime import datetime

import icalendar
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from aida_customs.tests import _factories as f


def _ics_attachment(msg):
    for filename, content, mimetype in msg.attachments:
        if "text/calendar" in mimetype:
            return content.encode() if isinstance(content, str) else content
    raise AssertionError("no text/calendar attachment on the message")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class IcsEmailTests(TestCase):
    def setUp(self):
        self.company = f.make_company()
        self.rec = f.make_recruitment(self.company)
        self.cand = f.make_candidate(self.rec)
        self.A = f.make_employee(self.company, email="alice@aidachip.com")

    def test_scheduling_emails_valid_ics_to_interviewer(self):
        mail.outbox = []
        # Attaching the interviewer (M2M post_add) is when the invite fires —
        # the real flow creates the schedule then adds interviewers.
        interview = f.make_interview(self.cand, interviewers=[self.A])

        self.assertEqual(len(mail.outbox), 1, "exactly one invite email expected")
        msg = mail.outbox[-1]
        self.assertIn("alice@aidachip.com", msg.to)

        cal = icalendar.Calendar.from_ical(_ics_attachment(msg))
        vevent = next(c for c in cal.walk() if c.name == "VEVENT")

        expected = timezone.make_aware(
            datetime.combine(interview.interview_date, interview.interview_time),
            timezone.get_current_timezone(),
        )
        self.assertEqual(vevent["DTSTART"].dt, expected)  # exact, not "contains"
        attendees = vevent.get("ATTENDEE")
        attendee_list = attendees if isinstance(attendees, list) else [attendees]
        emails = [str(a).replace("MAILTO:", "") for a in attendee_list]
        self.assertIn("alice@aidachip.com", emails)
        # KILL-NOTE: break the date+time -> DTSTART combine (e.g. swap to
        # datetime.now()) -> DTSTART assertion RED. Drop msg.attach(...) ->
        # _ics_attachment raises -> RED.

    def test_no_candidate_pii_in_email_body_only_in_ics(self):
        # Amin: EmailLog logs subject+body (untenanted, no retention) but NOT
        # the attachment. Candidate name / interview date must appear ONLY in
        # the .ics, never in the logged subject/body.
        mail.outbox = []
        interview = f.make_interview(self.cand, interviewers=[self.A])
        msg = mail.outbox[-1]
        name = self.cand.name
        iso_date = str(interview.interview_date)

        # Logged surfaces carry NO candidate PII.
        self.assertNotIn(name, msg.subject)
        self.assertNotIn(name, msg.body)
        self.assertNotIn(iso_date, msg.subject)
        self.assertNotIn(iso_date, msg.body)

        # The attachment (not logged) still carries the full details.
        ics_text = _ics_attachment(msg).decode()
        self.assertIn(name, ics_text)
        # KILL-NOTE: put the candidate name/date back in the subject or body ->
        # the assertNotIn assertions go RED (PII would re-enter EmailLog).

    def test_marking_completed_does_not_resend(self):
        interview = f.make_interview(self.cand, interviewers=[self.A])  # initial invite
        mail.outbox = []
        interview.completed = True
        interview.save()  # not a reschedule -> no new email
        self.assertEqual(len(mail.outbox), 0)
        # KILL-NOTE: send unconditionally on post_save -> a non-reschedule save
        # resends -> RED.
