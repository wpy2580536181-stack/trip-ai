"""Serialization utilities for SQLAlchemy models

This module provides:
1. _count attachment (mimicking Prisma's include: { _count: {...} } feature)
2. CamelCase serialization support (snake_case -> camelCase)
"""

from typing import List, Dict, Tuple, Type, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase


async def attach_count(
    session: AsyncSession,
    items: List[Any],
    count_model_cls: Type[DeclarativeBase],
    fk_field: str,
    group_field: str = "id",
    count_name: str = "items"
) -> List[Dict]:
    """Attach _count field to SQLAlchemy objects (mimicks Prisma's _count)
    
    Args:
        session: AsyncSession
        items: List of SQLAlchemy objects
        count_model_cls: The model class to count (e.g., Message)
        fk_field: Foreign key field name in count_model_cls (e.g., "conversation_id")
        group_field: Field name in items to group by (default: "id")
        count_name: Name for the count (default: "items")
    
    Returns:
        List of dicts with _count attached (always present, even if 0)
        
    Example:
        # Mimic Prisma: include: { _count: { select: { messages: true } } }
        conversations = await get_conversations()
        result = await attach_count(
            session, 
            conversations, 
            Message, 
            fk_field="conversation_id",
            count_name="messages"
        )
        # result[0] = {"id": 1, ..., "_count": {"messages": 5}}
    """
    
    # Attach _count to each item (always include _count key)
    result_list = []
    
    if not items:
        return result_list
    
    try:
        # Get IDs from items
        ids = [getattr(item, group_field) for item in items]
        
        # Query count
        fk_column = getattr(count_model_cls, fk_field)
        stmt = (
            select(fk_column, func.count().label("cnt"))
            .where(fk_column.in_(ids))
            .group_by(fk_column)
        )
        result = await session.execute(stmt)
        count_map = {row[0]: row[1] for row in result}
        
        # Attach _count to each item
        for item in items:
            item_dict = dict(item.__dict__)
            # Remove SQLAlchemy internal state
            item_dict.pop("_sa_instance_state", None)
            
            # Attach _count (always present)
            item_dict["_count"] = {
                count_name: count_map.get(getattr(item, group_field), 0)
            }
            result_list.append(item_dict)
    except Exception as e:
        # If query fails, still return items with _count = 0
        for item in items:
            item_dict = dict(item.__dict__)
            item_dict.pop("_sa_instance_state", None)
            item_dict["_count"] = {count_name: 0}
            result_list.append(item_dict)
    
    return result_list


def to_camel(s: str) -> str:
    """Convert snake_case to camelCase
    
    Args:
        s: snake_case string
        
    Returns:
        camelCase string
        
    Example:
        >>> to_camel("user_id")
        'userId'
        >>> to_camel("created_at")
        'createdAt'
    """
    parts = s.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


# Pydantic v2 CamelCase support
try:
    from pydantic import AliasGenerator
    
    # This is the recommended way in Pydantic v2
    # Use in your schema:
    #
    # from pydantic import BaseModel, ConfigDict
    # from pydantic.alias_generators import to_camel as pydantic_to_camel
    #
    # class CamelModel(BaseModel):
    #     model_config = ConfigDict(
    #         alias_generator=pydantic_to_camel,
    #         populate_by_name=True,
    #         from_attributes=True
    #     )
    # 
    # class UserResponse(CamelModel):
    #     id: int
    #     user_id: int  # Serializes to "userId"
    #     created_at: datetime  # Serializes to "createdAt"
    
    PYDANTIC_V2_AVAILABLE = True
except ImportError:
    PYDANTIC_V2_AVAILABLE = False


def serialize_to_camel(data: Dict) -> Dict:
    """Serialize a dict to camelCase keys
    
    Args:
        data: Dictionary with snake_case keys
        
    Returns:
        Dictionary with camelCase keys
        
    Example:
        >>> serialize_to_camel({"user_id": 1, "created_at": "2024-01-01"})
        {"userId": 1, "createdAt": "2024-01-01"}
    """
    result = {}
    for key, value in data.items():
        # Recursively serialize nested dicts
        if isinstance(value, dict):
            value = serialize_to_camel(value)
        elif isinstance(value, list):
            value = [
                serialize_to_camel(item) if isinstance(item, dict) else item
                for item in value
            ]
        
        # Convert key to camelCase
        result[to_camel(key)] = value
    
    return result
