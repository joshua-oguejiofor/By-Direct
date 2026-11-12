"""
Product Service Module with Versioned-Key Caching Strategy.

Architecture & Caching Overview:
--------------------------------
This module implements a Cache Versioning Pattern to handle cache invalidation 
cleanly across the separate Redis and service layers, preventing stale stock views 
and targeted key deletion errors.

Key Design Principles:
1. Global Version Tracking: A central counter (`product_cache_version`) is stored in Redis.
2. Versioned Key Structure: All product-related cache keys (public views, admin views, lists, 
   and search results) incorporate the current version prefix: 
   eg. `v:{version}:product:{id}:admin={bool}`.
3. Atomic Invalidation: Whenever inventory changes—such as during checkout decrements, 
   expired order restocks, or admin updates—the cache version is atomically incremented 
   using `bump_product_cache_version()` helper in redis layer.
4. Instant Deprecation: Incrementing the version renders all prior cache keys instantly 
   inaccessible, eliminating stale data without needing complex or fragile key-matching deletions.
"""




import hashlib
import json
import logging
from math import ceil

from fastapi import BackgroundTasks
from slugify import slugify

from app.core import exceptions, redis_server
from app.domains.category.category_service import CategoryService
from app.models import Product, ProductImage, User
from app.shared.utility import admin_check, build_cache_key

from . import cloudinary_image
from .product_repository import ProductRepository
from .product_schema import CreateProduct, CreateProductImage, UpdateProduct

logger = logging.getLogger(__name__)

class ProductService:
    def __init__(self, product_repo: ProductRepository, category_service: CategoryService | None = None):
        self.product_repo = product_repo
        self.category_service = category_service

        
    # This will serve as a helper function for both this layers and external layer  
    async def _get_product_with_id(self, product_id: int, current_user: User) -> Product:
        
        
        is_admin = admin_check(current_user)
        
        db_product = await self.product_repo.get_product_by_id(product_id=product_id, is_admin=is_admin)
        
        if not db_product:
            raise exceptions.NotFoundError("Product not found")
        
        return db_product
    

    async def create_product(self, data: CreateProduct, admin_user: User) -> bool:
        
        if await self.product_repo.name_exist(data.name):
            raise exceptions.ConflictingError(f"Product {data.name} already exist.")
        category = await self.category_service.get_category_by_id(data.category_id)
        
        if data.stock_quantity == 0 and data.is_active == True:
            raise exceptions.BadRequestError("Quantity should not be 0 while the product is set to be active.")
        
        # Generate the slug from the name
        slug = slugify(data.name)
        
        # Extract image data and product data from the Pydantic schema and convert them to dictionary
        image_data = data.image.model_dump()
        product_data = data.model_dump(exclude={"image"}) # exclud the nested image from the schemma
        
        # Inject the generated slug into the product dictionary
        product_data["slug"] = slug
        product_data["category_id"] = category.id
        
        # Create the product instance, unpack the dictionary and save it first to generate the ID
        db_product = Product(**product_data)
        await self.product_repo.save_product(db_product)
        
        # Create and save the image using the new product's ID
        db_image = ProductImage(**image_data, product_id=db_product.id)
        await self.product_repo.save_product(db_image)
        logger.info(f"Product with id: {db_product.id} created by admin: {admin_user.id}")
        return True

    
    async def get_all_product(
    self, page: int, 
    page_size: int,  current_user: User | None
    ) -> dict:

        skip = (page - 1) * page_size

        is_admin = admin_check(current_user)
        

        version = await redis_server.get_product_cache_version()
        
        cache_key = f"v:{version}:all_products:{skip}:{page_size}:admin={is_admin}"
        
        cached = await redis_server.get_cache(cache_key)
        if cached:
            return cached
        
        db_products, total_count = await self.product_repo.get_products(
            offset=skip, limit=page_size, is_admin=is_admin
            )
        
        total_pages = ceil(total_count / page_size) if total_count > 0 else 0
        
        data = {
            "products": db_products, 
            "count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            }
        
        await redis_server.set_cache(key=cache_key, value=data)

        return data

    async def get_product_by_id(
        self, product_id: int, 
        current_user: User | None
        ) -> Product | dict: # dict from redis
        
        is_admin = admin_check(current_user)
        version = await redis_server.get_product_cache_version()      
        cache_key = f"v:{version}:product:{product_id}:admin={is_admin}"
                
        cached = await redis_server.get_cache(cache_key)
        if cached:
            return cached
        
        db_product = await self.product_repo.get_with_images(product_id=product_id, is_admin=is_admin)
        
        if not db_product:
            raise exceptions.NotFoundError(f"Product {product_id} not found")

        await redis_server.set_cache(key=cache_key, value=db_product)
        
        return db_product


    async def search_products(
        self,
        page: int,
        page_size: int,
        category_id: int,
        slug: str | None,
        current_user: User | None,
        query: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
    ) -> dict:
        skip = (page - 1) * page_size
        
        is_admin = admin_check(current_user)        
        
        params = {
        "slug": slug, "query": query,
        "category_id": str(category_id) if category_id is not None else None,
        "min_price": str(min_price) if min_price is not None else None,
        "max_price": str(max_price) if max_price is not None else None,
        "skip": skip, "page_size": page_size,
        "is_admin": is_admin,
        }
        canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        
        version = await redis_server.get_product_cache_version()
                
        cache_key = build_cache_key(f"v:{version}", f"product:search:{digest}")
        
        cached = await redis_server.get_cache(key=cache_key)
        if cached:
            return cached
        
        db_products, total_count = await self.product_repo.search(
            slug=slug, category_id=category_id,
            is_admin=is_admin,
            query=query, min_price=min_price, 
            max_price=max_price, 
            offset=skip, limit=page_size
            )
        
        total_pages = ceil(total_count / page_size) if total_count > 0 else 0
                
        data = {
            "products": db_products, 
            "count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            }
        await redis_server.set_cache(key=cache_key, value=data)
        return data


    async def update_product(self, product_id: int, data: UpdateProduct, admin_user: User) -> bool:
                
        db_product = await self._get_product_with_id(product_id=product_id, current_user=admin_user)
        if data.stock_quantity == 0 and data.is_active == True:
            raise exceptions.BadRequestError("Quantity should not be 0 while the product is set to be active.")
        
        # If updating only discount_price, compare against stored product.price
        new_price = data.price if data.price is not None else db_product.price
        new_discount = data.discount_price if data.discount_price is not None else db_product.discount_price

        if new_discount and new_discount >= new_price:
            raise exceptions.BadRequestError("Discount price must be less than the regular price.")
        
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(db_product, field, value)
            
        if data.name and await self.product_repo.name_exist(data.name, product_id=product_id):
            raise exceptions.ConflictingError(f"Product {data.name} already exist.")
        
        if data.name:
            db_product.slug = slugify(data.name)
            
        await redis_server.delete_cache(f"product:{product_id}")
        await self.product_repo.update_product(db_product)
        
        await redis_server.bump_product_cache_version()
        logger.info(f"Product with id: {db_product.id} updated by admin: {admin_user.id}")
        return True


    async def _update_product_rating_reviews(self, product_id: int, avg_rating: int, total_reviews: int, current_user: User) -> bool:
            
        db_product = await self._get_product_with_id(product_id=product_id, current_user=current_user)
        
        db_product.average_rating = round(float(avg_rating or 0), 2)
        db_product.total_reviews = total_reviews
        
        await redis_server.bump_product_cache_version()
        return True

    async def delete_product(self, product_id: int, superadmin: User, background_tasks: BackgroundTasks) -> bool:
        
        is_admin = admin_check(superadmin)
        cache_key = build_cache_key("product", str(product_id), f"admin={is_admin}")
        
        product = await self.product_repo.get_with_images(product_id=product_id, is_admin=is_admin)
        if not product:
            raise exceptions.NotFoundError("Product not found")

        public_ids = [img.public_id for img in product.images]   # read BEFORE the rows are deleted

        await self.product_repo.delete_object(product)
        await redis_server.delete_cache(cache_key)
        await redis_server.bump_product_cache_version()

        logger.info(f"Product with id: {product_id} deleted by admin: {superadmin.id}")
        
        background_tasks.add_task(cloudinary_image.delete_images, public_ids)
        
        return True


    async def add_image(self, product_id: int, data: CreateProductImage, admin_user: User) -> bool:
        await self._get_product_with_id(product_id=product_id, current_user=admin_user)
        if data.is_primary:
            await self.product_repo.unset_primary(product_id)
        elif await self.product_repo.count_images(product_id) == 0:
            data.is_primary = True                      # the first image is always the primary one
        await self.product_repo.save_product(ProductImage(**data.model_dump(), product_id=product_id))
        await redis_server.bump_product_cache_version()
        return True

    async def remove_image(self, product_id: int, image_id: int, admin_user: User, background_tasks: BackgroundTasks) -> str:
        """Returns the public_id so the route can delete it from Cloudinary after the commit."""
        await self._get_product_with_id(product_id=product_id, current_user=admin_user)
        image = await self.product_repo.get_image(product_id, image_id)
        if not image:
            raise exceptions.NotFoundError("Image not found")
        if await self.product_repo.count_images(product_id) <= 1:
            raise exceptions.BadRequestError("A product needs at least one image. Add a new one first.")
        public_id, was_primary = image.public_id, image.is_primary
        await self.product_repo.delete_object(image)
        if was_primary:                                 # promote another image
            first = await self.product_repo.first_image(product_id)
            first.is_primary = True
            await self.product_repo.update_product(first)
        await redis_server.bump_product_cache_version()
        
        background_tasks.add_task(cloudinary_image.delete_images, public_id)
        return True


    async def restock_product(self, product_id: int, quantity: int) -> bool:
        """ 
        This method is being called by order service when background runs it scheduled check
        for orders that it expiration has passed it limit, the product is restocked 
        
        """
        await self.product_repo.restock_expired_researve(product_id=product_id, quantity=quantity)
        await redis_server.bump_product_cache_version()
        logger.info(f"Product with id: {product_id} restoked from expired order")
        return True
    
    
    async def reserve_stock_for_user(self, product_id: int, quantity: int) -> int:
            """ 
            This method is being called by order service during checkout to reserve product for user            
            """
            result =  await self.product_repo.reserve_stock(product_id=product_id, quantity=quantity)
            return result
