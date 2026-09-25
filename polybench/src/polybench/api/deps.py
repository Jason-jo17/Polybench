from typing import Annotated
from collections.abc import Generator
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlmodel import Session

from polybench.db import get_api_session
from polybench.config import settings

# FastAPI Dependency for injecting SQLModel session
SessionDep = Annotated[Session, Depends(get_api_session)]

security = HTTPBasic(auto_error=False)

def verify_password(credentials: Annotated[HTTPBasicCredentials | None, Depends(security)]):
    if not settings.polybench_dashboard_password:
        return True
    
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    correct_password_bytes = settings.polybench_dashboard_password.encode("utf8")
    provided_password_bytes = credentials.password.encode("utf8")
    
    is_correct_password = secrets.compare_digest(
        correct_password_bytes, provided_password_bytes
    )
    
    if not is_correct_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True
