from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from pydantic import BaseModel
import jwt
import os
import secrets # <-- NEW: For cryptographically secure random keys

from database import get_db
import models

# --- SECURED CONFIGURATION ---
# Auto-generates a cryptographically secure 256-bit key if not provided via .env
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32)) 
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 # 24 Hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Tells FastAPI where the login endpoint is so the auto-generated docs work
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

router = APIRouter(tags=["Authentication"])

# --- SCHEMAS ---
class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str

# --- NEW: SCHEMA FOR PASSWORD CHANGE ---
class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# ==========================================
# --- THE SECURITY DEPENDENCIES ---
# ==========================================
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Verifies the JWT token and returns the user object. Rejects invalid/expired tokens."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or token expired",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception
    
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

def get_current_admin(current_user: models.User = Depends(get_current_user)):
    """A secondary check that ensures the user is an Administrator."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Administrator privileges required to perform this action."
        )
    return current_user
# ==========================================


@router.post("/auth/token")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.username, "role": user.role})
    
    # --- SECURED: Return the trap flag to React ---
    return {
        "access_token": access_token, 
        "token_type": "bearer", 
        "role": user.role,
        "requires_password_change": user.requires_password_change 
    }

@router.post("/auth/users")
def create_new_user(request: UserCreateRequest, db: Session = Depends(get_db), current_admin: models.User = Depends(get_current_admin)):
    """Allows an Admin to create a new user. Notice the current_admin dependency!"""
    existing_user = db.query(models.User).filter(models.User.username == request.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists.")
    
    hashed_pw = pwd_context.hash(request.password)
    new_user = models.User(username=request.username, hashed_password=hashed_pw, role=request.role)
    db.add(new_user)
    db.commit()
    
    return {"message": f"User '{request.username}' created successfully as a {request.role}."}

# --- NEW: THE PASSWORD CHANGE PIPELINE ---
@router.post("/auth/change-password")
def change_password(request: PasswordChangeRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if not verify_password(request.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    
    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters long")
        
    current_user.hashed_password = pwd_context.hash(request.new_password)
    current_user.requires_password_change = False
    db.commit()
    
    return {"message": "Password updated successfully. Network secured."}