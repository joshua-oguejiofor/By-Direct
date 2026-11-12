import logging
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.core.config import settings

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]), # protect against HTML injection/XSS.
    auto_reload=False, # reloads the template when modified(set True on development)
    undefined=StrictUndefined, # helps protect undefined jinja context
)


class BaseEmail:
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD.get_secret_value()
        self.from_email = settings.EMAILS_FROM


    def _render_template(self, template_name: str, context: dict) -> str:
        # Merge global default context with user-supplied context
        default_context = {
            "current_year": datetime.now(UTC).year,
            "store_name": settings.PROJECT_NAME
            }
        
        full_context = {**default_context, **context} # Unpack both dictionary as one
        logger.info(f"Rendering template: {template_name}")
        template = env.get_template(template_name)
        return template.render(full_context)


    async def send_email(self, to_email: str, subject: str, body: str) -> bool:
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = self.from_email
        msg['To'] = to_email

        msg.set_content(body, subtype='html')

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                start_tls=settings.SMTP_TLS,
            )
            logger.info(f"Email '{subject}' successfully sent to {to_email}")
            return True

        except aiosmtplib.SMTPException as e:
            logger.error(f"SMTP error while sending '{subject}' to {to_email}: {e}")
            raise
            
        except Exception as e:
            logger.error(f"Unexpected error while sending email to {to_email}: {e}")
            raise 