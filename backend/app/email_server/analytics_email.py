from app.core.config import settings

from .base_email import BaseEmail


class AnalyticsEmail(BaseEmail):
    def __init__(self):
        super().__init__()
        
        
    async def montly_analysis_report(self, overview: dict, growth: dict):
        
        html_body = self._render_template(
            template_name="analytics/analytics_report.html",
            context={"overview": overview, "growth": growth, "first_name": settings.SUPERADMIN_FIRST_NAME}
        )
        return await self.send_email(settings.SUPERADMIN_EMAIL, "Montly Report", html_body)