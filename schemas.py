"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional

# Example schemas (replace with your own):

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Booking schema for consultant appointments
class Booking(BaseModel):
    """
    Bookings collection schema
    Collection name: "booking"
    Stores appointment bookings in UTC while enforcing IST business rules.
    """
    name: str = Field(..., description="Client full name", min_length=2, max_length=100)
    email: EmailStr = Field(..., description="Client email")
    phone: Optional[str] = Field(None, description="Client phone number")
    date_ist: str = Field(..., description="Date in IST, format YYYY-MM-DD")
    start_time_ist: str = Field(..., description="Start time in IST, format HH:MM (24h)")
    start_utc_iso: str = Field(..., description="Start datetime in UTC ISO format")
    end_utc_iso: str = Field(..., description="End datetime in UTC ISO format")
    notes: Optional[str] = Field(None, description="Optional notes from client")
