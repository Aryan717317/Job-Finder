from __future__ import annotations

import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from services.scraper.app import db


def _build_html_table(rows: list[dict]) -> str:
    body_rows = []
    for row in rows:
        title = escape(row.get("title") or "Unknown")
        company = escape(row.get("company") or "Unknown")
        platform = escape(row.get("platform") or "")
        location = escape(row.get("location") or "")
        salary = escape(row.get("salary_text") or "")
        link = row.get("url") or "#"
        safe_link = escape(link, quote=True)
        body_rows.append(
            f"<tr>"
            f"<td>{platform}</td>"
            f"<td>{title}</td>"
            f"<td>{company}</td>"
            f"<td>{location}</td>"
            f"<td>{salary}</td>"
            f"<td><a href=\"{safe_link}\">Open</a></td>"
            f"</tr>"
        )

    table_rows = "".join(body_rows)
    return f"""
    <html>
      <body>
        <h2>New Job Alerts</h2>
        <p>Here are the latest {len(rows)} jobs discovered by your aggregator.</p>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; font-family: Arial, sans-serif; font-size: 14px;">
          <thead>
            <tr style="background: #f0f0f0;">
              <th>Platform</th>
              <th>Job Title</th>
              <th>Company</th>
              <th>Location</th>
              <th>Salary</th>
              <th>Link</th>
            </tr>
          </thead>
          <tbody>
            {table_rows}
          </tbody>
        </table>
      </body>
    </html>
    """


def send_new_jobs_email() -> int:
    db.init_db()
    rows = db.list_unnotified_jobs(limit=500)
    if not rows:
        db.log_email_notification(
            status="skipped_no_jobs",
            job_count=0,
            recipient="",
            subject="Job Aggregator: 0 New Jobs",
            error_message=None,
        )
        return 0

    sender = os.getenv("GMAIL_SENDER", "").strip()
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()
    recipient = os.getenv("GMAIL_RECIPIENT", "").strip() or sender
    max_retries = max(1, int(os.getenv("EMAIL_MAX_RETRIES", "3")))
    retry_delay = max(0.5, float(os.getenv("EMAIL_RETRY_DELAY_SECONDS", "2.0")))

    if not sender or not app_password or not recipient:
        raise RuntimeError("Set GMAIL_SENDER, GMAIL_APP_PASSWORD, and GMAIL_RECIPIENT in environment.")

    jobs = [dict(row) for row in rows]
    html = _build_html_table(jobs)
    subject = f"Job Aggregator: {len(jobs)} New Jobs"

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.attach(MIMEText(html, "html"))

    last_error: str | None = None
    for attempt in range(1, max_retries + 1):
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(sender, app_password)
                smtp.sendmail(sender, [recipient], message.as_string())
            break
        except Exception as exc:
            last_error = str(exc)
            db.log_email_notification(
                status=f"failed_attempt_{attempt}",
                job_count=len(jobs),
                recipient=recipient,
                subject=subject,
                error_message=last_error,
            )
            if attempt == max_retries:
                raise RuntimeError(f"Email send failed after {max_retries} attempts: {last_error}") from exc
            time.sleep(retry_delay * attempt)

    marked = db.mark_jobs_notified([job["external_id"] for job in jobs])
    db.log_email_notification(
        status="sent",
        job_count=marked,
        recipient=recipient,
        subject=subject,
        error_message=last_error,
    )
    return marked
