"""F2 — email interviewers a calendar invite when an interview is scheduled.

Horilla's interview scheduling sends no email today (only notify.send) and its
HorillaMailTemplate is body-only (cannot attach). So we hook a post_save signal
on recruitment.InterviewSchedule (staying out of the core view for clean
upstream merges), compose an EmailMessage with a text/calendar (.ics)
attachment, and send it through Horilla's configured SMTP — Django's send()
routes through EMAIL_BACKEND = base.backends.ConfiguredEmailBackend, which reads
DynamicEmailConfiguration, so creds and EmailLog behavior stay consistent.

Fires on create and on a genuine reschedule (interview_date/time changed), not
on unrelated saves (e.g. marking completed) — a pre_save snapshot detects the
change. Send failures are logged loudly and never swallow-and-continue silently.
"""

import logging

from django.core.mail import EmailMessage
from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver

from aida_customs.ics import build_ics
from recruitment.models import InterviewSchedule

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=InterviewSchedule)
def _snapshot_schedule(sender, instance, **kwargs):
    """Stash the persisted date/time so post_save can detect a reschedule."""
    if not instance.pk:
        instance._aida_old_slot = None
        return
    old = (
        sender.objects.filter(pk=instance.pk)
        .values("interview_date", "interview_time")
        .first()
    )
    instance._aida_old_slot = (
        (old["interview_date"], old["interview_time"]) if old else None
    )


@receiver(m2m_changed, sender=InterviewSchedule.employee_id.through)
def _email_on_interviewers_added(sender, instance, action, pk_set, **kwargs):
    """Interviewers are attached via M2M AFTER the row is created, so this — not
    post_save(created=True) — is when an interview first has recipients."""
    if action == "post_add" and pk_set:
        _send_invite(instance)


@receiver(post_save, sender=InterviewSchedule)
def _email_on_reschedule(sender, instance, created, **kwargs):
    """Re-send to the existing interviewers only when the slot actually moved."""
    if created:
        return  # nothing to send yet — no interviewers attached
    old_slot = getattr(instance, "_aida_old_slot", None)
    new_slot = (instance.interview_date, instance.interview_time)
    if old_slot is not None and old_slot != new_slot:
        _send_invite(instance)


def _recipient_emails(interview) -> list[str]:
    # Interviewers only. Naming interviewers to the candidate is a separate
    # disclosure (plan §10(e), founder/Amin) — candidate is intentionally not a
    # recipient here.
    emails = []
    for interviewer in interview.employee_id.all():
        email = interviewer.get_mail()
        if email:
            emails.append(email)
    return emails


def _send_invite(interview) -> None:
    recipients = _recipient_emails(interview)
    if not recipients:
        logger.warning(
            "Interview %s has no interviewer emails; ICS invite not sent.",
            interview.pk,
        )
        return
    try:
        ics = build_ics(interview)
        msg = EmailMessage(
            subject=f"Interview scheduled: {interview.candidate_id.name}",
            body=(
                f"An interview has been scheduled for "
                f"{interview.candidate_id.name} on {interview.interview_date} "
                f"at {interview.interview_time}. The calendar invite is attached."
            ),
            to=recipients,
        )
        msg.attach("interview.ics", ics, "text/calendar; method=REQUEST")
        msg.send(fail_silently=False)  # fail closed and loud
    except Exception:
        # Surface loudly; do not pretend the invite went out.
        logger.exception("Failed to send interview ICS invite for %s", interview.pk)
        raise
