"""Models package — import all models here so Alembic can detect them."""
from app.models.base import Base, TimestampMixin  # noqa: F401
from app.models.user import User, UserRole  # noqa: F401
from app.models.tour import Tour  # noqa: F401
from app.models.scene import Scene  # noqa: F401
from app.models.scene_link import SceneLink  # noqa: F401
from app.models.image_upload import ImageUpload, UploadStatus  # noqa: F401

__all__ = [
    "Base",
    "TimestampMixin",
    "User",
    "UserRole",
    "Tour",
    "Scene",
    "SceneLink",
    "ImageUpload",
    "UploadStatus",
]
