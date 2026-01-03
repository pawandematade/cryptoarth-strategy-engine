"""
Standardized API Response Models and Helpers
Ensures all user-facing APIs return consistent response format.
"""
from typing import Any, Optional, Dict, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar('T')


class StandardResponse(BaseModel, Generic[T]):
    """
    Standard response model for all user-facing APIs.
    
    All APIs MUST return:
    {
        "success": true,
        "data": <payload>,
        "message": "optional"
    }
    """
    success: bool
    data: T
    message: Optional[str] = None


def success(data: Any = None, message: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a standardized success response.
    
    All user-facing APIs MUST return:
    {
        "success": true,
        "data": <payload>,
        "message": "optional"
    }
    
    Args:
        data: Response payload (can be dict, list, or any serializable object)
        message: Optional message string
        
    Returns:
        dict: Standardized success response
        
    Example:
        return success({"credits": 100})
        return success([...], "Retrieved 10 items")
    """
    resp: Dict[str, Any] = {
        "success": True,
        "data": data
    }
    if message:
        resp["message"] = message
    return resp


def error(message: str, status_code: int = 400) -> Dict[str, Any]:
    """
    Create a standardized error response.
    
    Args:
        message: Error message
        status_code: HTTP status code (default: 400)
        
    Returns:
        dict: Standardized error response
        
    Example:
        return error("Invalid request", 400)
    """
    return {
        "success": False,
        "message": message,
        "status_code": status_code
    }

