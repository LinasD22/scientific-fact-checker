from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str

# Schema for the login request
class LoginRequest(BaseModel):
    email: str
    password: str