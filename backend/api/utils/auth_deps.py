from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlmodel import Session, select

from api.db.database import engine
from api.db.models import User
from api.utils.password_security import ALGORITHM, SECRET_KEY

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def get_optional_user_id(token: str | None = Depends(oauth2_scheme)) -> int | None:
    """Decode the Bearer token (if present) and return the matching User.id, or None for guests."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str | None = payload.get("sub")
        if not email:
            return None
    except JWTError:
        return None
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        return user.id if user else None


def get_required_user_id(token: str | None = Depends(oauth2_scheme)) -> int:
    """Decode the Bearer token and return User.id. Raises HTTP 401 if missing or invalid."""
    user_id = get_optional_user_id(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id
