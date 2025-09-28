from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
import os

router = APIRouter()

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "password")

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
def login(data: LoginRequest, response: Response):
    if data.username == ADMIN_USER and data.password == ADMIN_PASS:
        response.set_cookie(key="session", value="valid_admin_session", httponly=True, samesite="strict")
        return {"message": "Login successful"}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="session")
    return {"message": "Logged out successfully"}