"""
SonIA Core - Email Sender Module
Sends tracking reports and Excel files via email (SMTP).
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class EmailSender:
    """Sends emails with optional file attachments via SMTP."""

    def __init__(self, smtp_host: str, smtp_port: int, smtp_user: str,
                 smtp_password: str, from_email: str, from_name: str = "SonIA - BloomsPal"):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email
        self.from_name = from_name

    def _connect(self) -> smtplib.SMTP:
        """Create SMTP connection with TLS."""
        server = smtplib.SMTP(self.smtp_host, self.smtp_port)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(self.smtp_user, self.smtp_password)
        return server

    def send_report_email(self, to_email: str, client_name: str,
                          report_text: str, excel_path: Optional[str] = None) -> bool:
        """Send a tracking report email with optional Excel attachment."""
        try:
            msg = MIMEMultipart()
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to_email
            msg["Subject"] = f"SonIA Tracker - Reporte diario {client_name}"

            html_body = self._build_html_body(client_name, report_text)
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            if excel_path:
                self._attach_file(msg, excel_path)

            server = self._connect()
            server.sendmail(self.from_email, to_email, msg.as_string())
            server.quit()

            logger.info(f"Email sent to {to_email} for {client_name}")
            return True

        except Exception as e:
            logger.error(f"Email send error to {to_email}: {e}")
            return False

    def send_file_email(self, to_email: str, file_path: str,
                        subject: str, body_text: str = "") -> bool:
        """Send an email with a file attachment."""
        try:
            msg = MIMEMultipart()
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to_email
            msg["Subject"] = subject

            if body_text:
                msg.attach(MIMEText(body_text, "plain", "utf-8"))

            self._attach_file(msg, file_path)

            server = self._connect()
            server.sendmail(self.from_email, to_email, msg.as_string())
            server.quit()

            logger.info(f"File email sent to {to_email}: {subject}")
            return True

        except Exception as e:
            logger.error(f"File email send error to {to_email}: {e}")
            return False

    def _attach_file(self, msg: MIMEMultipart, file_path: str):
        """Attach a file to the email message."""
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"Attachment file not found: {file_path}")
            return

        with open(file_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{path.name}"',
        )
        msg.attach(part)

    def _build_html_body(self, client_name: str, report_text: str) -> str:
        """Convert plain-text report to a simple HTML email body."""
        escaped = (report_text
                   .replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;"))
        html_report = escaped.replace("\n", "<br>\n")

        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto;">
    <div style="background-color: #2E7D32; color: white; padding: 15px 20px; border-radius: 8px 8px 0 0;">
        <h2 style="margin: 0;">SonIA Tracker</h2>
        <p style="margin: 5px 0 0 0; font-size: 14px;">Reporte diario de tracking - {client_name}</p>
    </div>
    <div style="padding: 20px; background-color: #f9f9f9; border: 1px solid #e0e0e0;">
        <pre style="font-family: Courier New, monospace; font-size: 13px; white-space: pre-wrap; word-wrap: break-word; line-height: 1.5;">
{html_report}
        </pre>
    </div>
    <div style="padding: 10px 20px; background-color: #e8e8e8; border-radius: 0 0 8px 8px; font-size: 12px; color: #666;">
        <p style="margin: 0;">SonIA - BloomsPal | Reporte generado automaticamente</p>
        <p style="margin: 3px 0 0 0;">Si tienes preguntas, responde a este correo o contactanos por WhatsApp.</p>
    </div>
</body>
</html>"""
