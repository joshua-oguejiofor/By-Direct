import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

class AppException(Exception):
    status_code: int = 500

    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(msg)


class BadRequestError(AppException):
    status_code = 400

class NotFoundError(AppException):
    status_code = 404

class UnauthorizedError(AppException):
    status_code = 401

class ForbiddenError(AppException):
    status_code = 403
    
class ConflictingError(AppException):
    status_code = 409
    
class BadGatewayError(AppException):
    status_code = 502

class GatewayTimeoutError(AppException):
    status_code = 504





def register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": True,
                "msg": "Validation Error",
                "details":  jsonable_encoder(exc.errors()), # to josnify the error response
            },
        )
    
    @app.exception_handler(AppException)
    async def app_exception_handlers(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": True,
                "msg": exc.msg
            }
        )
        

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # This automatically captures the traceback and logs it safely ensures sensitive internal error details are not sent in the API response.
        logger.exception(f"Unhandled error occurred on path: { request.url.path}")
        
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "msg": "Something went wrong, try again later."
            }
        )