"""Custom exceptions for FastAPI"""

from fastapi import status


class AppException(Exception):
    """Base application exception"""
    
    def __init__(
        self,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        code: int = 500,
        message: str = "Internal server error",
        error: str = None
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.error = error
        super().__init__(message)


class NotFoundException(AppException):
    """Resource not found exception"""
    
    def __init__(self, resource: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            code=404,
            message=f"{resource} not found",
            error="NOT_FOUND"
        )


class UnauthorizedException(AppException):
    """Authentication required exception"""
    
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=401,
            message="Authentication required",
            error="UNAUTHORIZED"
        )


class ForbiddenException(AppException):
    """Admin access required exception"""
    
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code=403,
            message="Admin access required",
            error="FORBIDDEN"
        )


class BadRequestException(AppException):
    """Bad request exception"""
    
    def __init__(self, message: str = "Bad request"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=400,
            message=message,
            error="BAD_REQUEST"
        )


class ConflictException(AppException):
    """Resource conflict exception (e.g., duplicate)"""
    
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code=409,
            message=message,
            error="CONFLICT"
        )
