"""Global exception handlers for FastAPI"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from jwt import InvalidTokenError, ExpiredSignatureError
from src.exceptions import AppException


def setup_exception_handlers(app: FastAPI):
    """Register all exception handlers with the FastAPI app"""
    
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        """Handle custom AppException"""
        
        # Determine response format based on path
        path = request.url.path
        
        # Format A: {success, data, error} for specific paths
        if is_format_a(path):
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "success": False,
                    "data": None,
                    "error": exc.message
                }
            )
        
        # Format B: {code, data, message, error}
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "data": None,
                "message": exc.message,
                "error": exc.error
            }
        )
    
    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        """Handle database integrity errors (duplicate, foreign key, etc.)"""
        
        error_msg = str(exc.orig) if hasattr(exc, 'orig') else str(exc)
        
        # Check if it's a duplicate error
        if "Duplicate entry" in error_msg or "UNIQUE constraint failed" in error_msg:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "code": 409,
                    "data": None,
                    "message": "Resource already exists",
                    "error": "DUPLICATE_ENTRY"
                }
            )
        
        # Foreign key violation
        if "Cannot add or update a child row" in error_msg or "FOREIGN KEY constraint failed" in error_msg:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "code": 400,
                    "data": None,
                    "message": "Invalid reference",
                    "error": "FOREIGN_KEY_VIOLATION"
                }
            )
        
        # Generic integrity error
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "code": 400,
                "data": None,
                "message": "Data integrity error",
                "error": "INTEGRITY_ERROR"
            }
        )
    
    @app.exception_handler(InvalidTokenError)
    @app.exception_handler(ExpiredSignatureError)
    async def jwt_error_handler(request: Request, exc: Exception):
        """Handle JWT errors"""
        
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "code": 401,
                "data": None,
                "message": "Invalid or expired token",
                "error": "UNAUTHORIZED"
            }
        )
    
    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
        """Handle generic SQLAlchemy errors"""
        
        # Don't expose internal details in production
        from src.config.settings import settings
        
        error_msg = str(exc) if settings.node_env == "development" else "Database error"
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": 500,
                "data": None,
                "message": error_msg,
                "error": "DATABASE_ERROR"
            }
        )
    
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """Catch-all exception handler"""
        
        from src.config.settings import settings
        
        # Log the error
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        
        # Don't expose internal details in production
        if settings.node_env == "production":
            message = "Internal server error"
            error = "INTERNAL_ERROR"
        else:
            message = str(exc)
            error = type(exc).__name__
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": 500,
                "data": None,
                "message": message,
                "error": error
            }
        )


def is_format_a(path: str) -> bool:
    """Check if the path should use response format A
    
    Format A: {success, data, error}
    Format B: {code, data, message, error}
    
    Paths using format A:
    - /api/trip/recommend
    - /api/trip/optimize
    """
    
    format_a_paths = [
        "/api/trip/recommend",
        "/api/trip/optimize"
    ]
    
    return any(path.startswith(p) for p in format_a_paths)
