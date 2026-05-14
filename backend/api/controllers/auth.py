from fastapi import FastAPI, Depends, HTTPException, status, APIRouter, Header, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select, delete
from api.db.database import engine
from api.db.models import User, Auth, TokenBlacklist, Subscription
from api.schemas.user import UserCreate, LoginRequest
from api.utils.password_security import hash_password, verify_password, create_access_token
from pydantic import BaseModel
from api.db.database import get_session
from api.utils.password_security import decode_access_token
from jose import JWTError, ExpiredSignatureError

app = FastAPI()

# OAuth2 scheme for token extraction from requests
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Creating 'router' attribute that application.py is looking for
router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

# # Dependency to get a database session
# def get_session():
#     with Session(engine) as session:
#         yield session

def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)):
    payload = decode_access_token(token)
    
    # Extract email
    email: str = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identity not found in token."
        )

    # Fetch user from DB
    user = session.exec(select(User).where(User.email == email)).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists."
        )

    return user

def get_subscription_info(user_id: int, user_email: str, session: Session):
    # Find the newest subscription record
    statement = (
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.id.desc())
    )
    latest_sub = session.exec(statement).first()

    if latest_sub and latest_sub.status_id == 1:
        return {
            "is_active": True,
            "plan": latest_sub.plan_name,
            "queries_performed": latest_sub.queries_performed,
            "renewal_time": latest_sub.renewal_time
        }

    return {
        "is_active": False,
        "plan": "free",
        "queries_performed": 0,
        "renewal_time": None
    }

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(user_data: UserCreate, session: Session = Depends(get_session)):
    # Check if user already exists
    existing_user = session.exec(select(Auth).where(Auth.email == user_data.email)).first()
    if existing_user:
        raise HTTPException(
            status_code=400, 
            detail="A user with this email already exists."
        )

    # Create the Auth record (hashed password)
    new_auth = Auth(
        email=user_data.email,
        password=hash_password(user_data.password)
    )
    session.add(new_auth)
    
    # Create the User record
    new_user = User(
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        email=user_data.email,
        auth_email=new_auth.email,
        stripe_customer_id=None  # Will be set when they start a checkout session
    )
    session.add(new_user)
    
    try:
        session.commit()
        session.refresh(new_user)
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Database error during registration.")

    # Generate JWT Token (logged in immediately)
    access_token = create_access_token(data={"sub": new_user.email})

    # Get initial subscription info (default free)
    sub_info = get_subscription_info(new_user.id, new_user.email, session)

    return {
        "message": "User registered successfully",
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": new_user.id,
        "subscription": sub_info
    }

@router.post("/login")
def login(data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    # Look for the user in the Auth table
    # OAuth2PasswordRequestForm uses 'username' for the email field
    statement = select(Auth).where(Auth.email == data.username)
    user_auth = session.exec(statement).first()
    
    # Check if user exists and password is correct
    if not user_auth or not verify_password(data.password, user_auth.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # get user object to return user_id in response
    user = session.exec(select(User).where(User.email == data.username)).first()

    if not user:
        raise HTTPException(status_code=404, detail="User profile not found")
    
    # get subscription info using helper
    sub_info = get_subscription_info(user.id, user.email, session)

    # Create JWT token
    # sub is unique identifier for the user, using user email here
    access_token = create_access_token(data={"sub": user_auth.email})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "subscription": sub_info
    }
    

def cleanup_blacklist(session: Session):
    # Delete everything where expires_at is in the past
    statement = delete(TokenBlacklist).where(TokenBlacklist.expires_at < datetime.now(timezone.utc))
    session.exec(statement)
    session.commit()


def logout(
    background_tasks: BackgroundTasks,
    data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session)
):
    # OAuth2PasswordRequestForm uses 'username' as the field name, even though we are using email for login
    statement = select(Auth).where(Auth.email == data.username)
    user_auth = session.exec(statement).first()
    
    if not user_auth or not verify_password(data.password, user_auth.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    access_token = create_access_token(data={"sub": user_auth.email})
    return {"access_token": access_token, "token_type": "bearer"}