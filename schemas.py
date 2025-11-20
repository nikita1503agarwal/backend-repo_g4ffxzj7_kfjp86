"""
Database Schemas for Prayer Retreat Accommodation Manager

Each Pydantic model represents a MongoDB collection.
Collection name is the lowercase of the class name:
- Room -> "room"
- Participant -> "participant"
- Assignment -> "assignment"
"""

from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal

class Room(BaseModel):
    """
    Rooms available for the 3-day retreat
    """
    name: str = Field(..., description="Room name or number")
    capacity: int = Field(..., ge=1, le=100, description="Max occupants")
    gender: Literal["male", "female", "mixed"] = Field("mixed", description="Allowed gender")
    type: Literal["dorm", "double", "private"] = Field("dorm", description="Room type")
    cooling: Literal["ventilated", "air_conditioned"] = Field(
        "ventilated", description="Room cooling type: ventilated fan room or air conditioned"
    )
    amenities: List[str] = Field(default_factory=list, description="Amenities like bathroom, AC, etc.")

class Participant(BaseModel):
    """
    Attendees of the retreat
    """
    full_name: str = Field(..., description="Full name")
    email: Optional[EmailStr] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    gender: Optional[Literal["male", "female"]] = Field(None, description="Participant gender")
    parish: Optional[str] = Field(None, description="Parish or community")
    special_needs: Optional[str] = Field(None, description="Accessibility or dietary needs")
    preference: Optional[Literal["dorm", "double", "private"]] = Field(None, description="Preferred room type")

class Assignment(BaseModel):
    """
    Assign a participant to a room for specific days of the 3-day retreat
    stay_days: list of day numbers in {1,2,3}
    """
    participant_id: str = Field(..., description="Participant ObjectId as string")
    room_id: str = Field(..., description="Room ObjectId as string")
    stay_days: List[int] = Field(..., description="Days assigned (subset of [1,2,3])")

# Note:
# - Use these schemas to structure and validate data.
# - The backend endpoints use these names as collection names (lowercased).
