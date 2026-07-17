from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from pydantic import BaseModel
import jwt
import os
import secrets
from cryptography.fernet import Fernet 
from database import get_db
import models
import schemas 

# --- IMPORT THE LOGGER ---
from logger import log_event

# --- SECURED CONFIGURATION ---
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32)) 
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 

# --- AES-256 DEVICE ENCRYPTION ENGINE ---
# Generates a persistent key, or uses a strict 32-byte url-safe base64 key
ENCRYPTION_KEY = os.getenv("VNMS_ENCRYPTION_KEY", "uO1v_Zt5pU7N2F_cO2J-jX9kQ4vT1aL8wE5mY0zP_B8=")
cipher_suite = Fernet(ENCRYPTION_KEY)

def encrypt_secret(plain_text: str):
    if not plain_text: return None
    return cipher_suite.encrypt(plain_text.encode()).decode()

def decrypt_secret(cipher_text: str):
    if not cipher_text: return os.getenv("DEVICE_PASSWORD", "Werfds123") # Fallback for old lab devices
    try:
        return cipher_suite.decrypt(cipher_text.encode()).decode()
    except:
        return os.getenv("DEVICE_PASSWORD", "Werfds123")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")
router = APIRouter(tags=["Authentication"])

class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str

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

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None: raise credentials_exception
    except jwt.InvalidTokenError: raise credentials_exception
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None: raise credentials_exception
    return user

def get_current_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin": raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator privileges required.")
    return current_user

@router.post("/auth/token")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        # Optional: You could log failed login attempts here if you wanted a strict security trail
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password", headers={"WWW-Authenticate": "Bearer"})
    
    # Log successful login
    log_event(
        db=db, event_type="System", severity="INFO", author=user.username,
        target_devices=[], details={"action": "User Logged In", "role": user.role}
    )

    access_token = create_access_token(data={"sub": user.username, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer", "role": user.role, "requires_password_change": user.requires_password_change}

@router.post("/auth/change-password")
def change_password(request: PasswordChangeRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if not verify_password(request.old_password, current_user.hashed_password): raise HTTPException(status_code=400, detail="Incorrect current password")
    if len(request.new_password) < 8: raise HTTPException(status_code=400, detail="New password must be at least 8 characters long")
    
    current_user.hashed_password = pwd_context.hash(request.new_password)
    current_user.requires_password_change = False
    db.commit()

    # Log the self-service password change
    log_event(
        db=db, event_type="System", severity="INFO", author=current_user.username,
        target_devices=[], details={"action": "Self-Service Password Change Completed"}
    )
    return {"message": "Password updated successfully. Network secured."}

# --- ADMIN USER MANAGEMENT ENDPOINTS ---
@router.post("/auth/users")
def create_new_user(request: UserCreateRequest, db: Session = Depends(get_db), current_admin: models.User = Depends(get_current_admin)):
    if db.query(models.User).filter(models.User.username == request.username).first(): raise HTTPException(status_code=400, detail="Username already exists.")
    
    new_user = models.User(username=request.username, hashed_password=pwd_context.hash(request.password), role=request.role, requires_password_change=True)
    db.add(new_user)
    db.commit()

    # Log user creation
    log_event(
        db=db, event_type="System", severity="WARNING", author=current_admin.username,
        target_devices=[], details={"action": "Created New User Account", "target_user": request.username, "assigned_role": request.role}
    )
    return {"message": f"User '{request.username}' created successfully."}

@router.get("/auth/users", response_model=list[schemas.UserResponse])
def get_all_users(db: Session = Depends(get_db), current_admin: models.User = Depends(get_current_admin)):
    return db.query(models.User).all()

@router.delete("/auth/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_admin: models.User = Depends(get_current_admin)):
    if current_admin.id == user_id: raise HTTPException(status_code=400, detail="Cannot delete your own account.")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user: raise HTTPException(status_code=404)
    
    target_username = user.username
    db.delete(user)
    db.commit()

    # Log user deletion
    log_event(
        db=db, event_type="System", severity="ERROR", author=current_admin.username,
        target_devices=[], details={"action": "Deleted User Account", "target_user": target_username}
    )
    return {"message": "User deleted"}

@router.put("/auth/users/{user_id}/password")
def admin_reset_password(user_id: int, request: schemas.AdminPasswordReset, db: Session = Depends(get_db), current_admin: models.User = Depends(get_current_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user: raise HTTPException(status_code=404)
    
    user.hashed_password = pwd_context.hash(request.new_password)
    user.requires_password_change = True # Springs the trap on them!
    db.commit()

    # Log admin password reset
    log_event(
        db=db, event_type="System", severity="WARNING", author=current_admin.username,
        target_devices=[], details={"action": "Admin Forced Password Reset", "target_user": user.username}
    )
    return {"message": "User password reset successfully."}