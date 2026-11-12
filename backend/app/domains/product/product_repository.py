from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Product, ProductImage


class ProductRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
    """
    The default for admin is False, 
    but get converted to True from service layer
    which will be checked in the "if not admin"
    """    
    
    # Atomic bulk update at DB level to avoid race conditions
    async def restock_expired_researve(self, product_id: int, quantity: int) -> None:
        return await self.db.execute(
            update(Product)
            .where(Product.id == product_id)
            .values(stock_quantity=Product.stock_quantity + quantity))
        
    # This will return the row count that wil be calculated on checkout
    async def reserve_stock(self, product_id: int, quantity: int) -> int:
        result = await self.db.execute(
            update(Product)
            .where(
                Product.id == product_id, 
                Product.stock_quantity >= quantity, 
                Product.is_active.is_(True)
                )
            .values(stock_quantity=Product.stock_quantity - quantity))
        
        return result.rowcount
                
    async def name_exist(self, name: str, product_id: int | None = None) -> bool:
        
        query = select(Product).where(Product.name == name)
            
        if product_id is not None:
            query = query.where(Product.id != product_id)
            
        result = await self.db.execute(select(query.exists()))
        return bool(result.scalar())
    
    
    async def get_product_by_id(self, product_id: int, is_admin: bool = False) -> Product | None:
        
        query = select(Product).where(Product.id == product_id)
            
        if not is_admin:
            query = query.where(Product.is_active == True)
                    
        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    async def get_with_images(self, product_id: int, is_admin: bool = False) -> Product | None:
          
        query = select(Product).options(
            selectinload(Product.images)
            ).where(
                Product.id == product_id
            )
        if not is_admin:
            query = query.where(Product.is_active == True)
            
        result = await self.db.execute(query)
        
        return result.scalar_one_or_none()


    async def get_products(
        self, 
        offset: int, 
        limit: int, 
        is_admin: bool = False
    )-> tuple[list[Product], int]:

        result = select(Product).options(selectinload(Product.images))
        count = select(func.count(Product.id))
        
        if not is_admin:
            result = result.where(Product.is_active.is_(True))
            count = count.where(Product.is_active.is_(True))

        result = result.offset(offset).limit(limit).order_by(Product.id.desc())

        products = (await self.db.execute(result)).scalars().all()
        total_count = (await self.db.execute(count)).scalar_one()

        return products, total_count


    async def search(
    self,
    offset: int,
    limit: int,
    category_id: int,
    is_admin: bool = False,
    slug: str | None = None,
    query: str | None = None, 
    min_price: float | None = None, 
    max_price: float | None = None, 
) -> tuple[list[Product], int]:
    
    # 1. Collect all dynamic filters into a list
        filters = []

        if query:
            filters.append(
                or_(
                    Product.name.ilike(f"%{query}%"),
                    Product.description.ilike(f"%{query}%"),
                    Product.brand.ilike(f"%{query}%"),
                )
            )
        if category_id is not None:
            filters.append(Product.category_id == category_id)
        if min_price is not None:
            filters.append(Product.price >= min_price)
        if max_price is not None:
            filters.append(Product.price <= max_price)
        if slug is not None:
            filters.append(Product.slug == slug)
        if not is_admin:
            filters.append(Product.is_active == True)
        
        # 2. Fast count query (no subquery, no unneeded selectinload)
        count_query = select(func.count(Product.id))
        if filters:
            count_query = count_query.where(*filters)
            
        total = (await self.db.execute(count_query)).scalar_one()
        
        
        # 3. Data query with selectinload applied ONLY here
        data_query = (
            select(Product)
            .options(selectinload(Product.images))
        )
        if filters:
            data_query = data_query.where(*filters)
            
        products = (await self.db.execute(
            data_query
            .offset(offset)
            .limit(limit)
            .order_by(Product.name)
        )).scalars().all()
            
        return products, total

    async def get_image(self, product_id: int, image_id: int) -> ProductImage | None:
        result = await self.db.execute(
            select(ProductImage)
            .where(
                ProductImage.id == image_id, 
                ProductImage.product_id == product_id
                )
        )
        return result.scalar_one_or_none()

    async def count_images(self, product_id: int) -> int:
        result = await self.db.execute(
            select(
                func.count(ProductImage.id))
            .where(ProductImage.product_id == product_id)
        )
        return result.scalar_one()

    async def unset_primary(self, product_id: int) -> None:
        await self.db.execute(
            update(ProductImage)
            .where(ProductImage.product_id == product_id)
            .values(is_primary=False)
        )

    async def first_image(self, product_id: int) -> ProductImage | None:
        result = await self.db.execute(
            select(ProductImage)
            .where(ProductImage.product_id == product_id)
            .order_by(ProductImage.id)
            .limit(1)
        )
        return result.scalar_one_or_none()






    async def save_product(self, obj: Product):
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
    
    
    async def update_product(self, obj: Product):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj


    async def delete_object(
        self, 
        obj: Product | ProductImage
        ) -> None:
        await self.db.delete(obj)
        await self.db.flush()
    
    