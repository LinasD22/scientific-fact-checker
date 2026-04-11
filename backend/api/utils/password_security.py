import os
from pathlib import Path
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from jose import jwt
import hashlib
from passlib.context import CryptContext

env_path = Path(__file__).resolve().parent /'.env'

# Load environment variables
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str):
    # Pre-hash with SHA256 to handle any password length
    prepared_password = hashlib.sha256(password.encode()).hexdigest()
    return pwd_context.hash(prepared_password)

def verify_password(plain_password, hashed_password):
    prepared_password = hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.verify(prepared_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    
    # Set expiration time 
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    # Sign the token with our Secret Key
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt