"""Models package - import all models to register with SQLAlchemy"""

from src.models.role import Role, RoleName
from src.models.user import User
from src.models.password_reset import PasswordReset
from src.models.trip import Trip
from src.models.conversation import Conversation
from src.models.message import Message
from src.models.spot import Spot
from src.models.feedback import Feedback
from src.models.agent_step import AgentStep

__all__ = [
    "Role",
    "RoleName",
    "User",
    "PasswordReset",
    "Trip",
    "Conversation",
    "Message",
    "Spot",
    "Feedback",
    "AgentStep",
]

# Import all models to ensure they are registered with SQLAlchemy
# This allows Alembic to detect all models for migrations
