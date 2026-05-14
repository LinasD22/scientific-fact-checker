# --- API SCHEMAS for data validation (Not Tables) ---
from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str

# Schema for the login request
class LoginRequest(BaseModel):
    email: EmailStr
    password: str