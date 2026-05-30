from fastapi import HTTPException, Depends
from app.auth_utils import get_current_user

ROLE_PERMISSIONS = {
    "admin": ["read", "upload", "edit", "delete", "export", "manage_users"],
    "broker": ["read", "upload", "edit", "export"],
    "underwriter": ["read", "export"],
    "viewer": ["read"],
    "user": ["read", "upload", "edit", "export", "manage_users"],
}


def require_permission(permission: str):
    def checker(current_user: dict = Depends(get_current_user)):
        role = current_user.get("role", "viewer")
        permissions = ROLE_PERMISSIONS.get(role, [])

        if permission not in permissions:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to perform this action.",
            )

        return current_user

    return checker