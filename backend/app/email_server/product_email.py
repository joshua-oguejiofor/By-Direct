from app.core.config import settings

from .base_email import BaseEmail


class ProductEmail(BaseEmail):
    def __init__(self):
        super().__init__()




    async def low_stock_alart(self, low_product_object: object):
        html_body = self._render_template(
            template_name="product/low_stock.html",
            context={
                "admin_name": settings.SUPERADMIN_FIRST_NAME,
                "dashboard_url": f"{settings.FRONTEND_URL}/products/inventory",
                "low_stock_items": low_product_object
                }
            )
        return await self.send_email(settings.SUPERADMIN_EMAIL, "Low stock alart", html_body)