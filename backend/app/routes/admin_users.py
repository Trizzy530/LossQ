import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.organization import Organization
from app.models.user import User
from app.routes.auth import get_current_user, require_admin_or_owner, public_user
from app.services.audit_service import write_audit_event

router = APIRouter(prefix="/admin-users", tags=["Admin Users"])

LOSSQ_SAFE_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def lossq_safe_sql_identifier(identifier: str) -> str:
    if not LOSSQ_SAFE_SQL_IDENTIFIER_RE.match(str(identifier or "")):
        raise HTTPException(status_code=500, detail="Unsafe database identifier")
    return f'"{identifier}"'


def lossq_delete_rows_by_column(
    db: Session,
    table_name: str,
    column_name: str,
    value_name: str,
    value: int,
) -> int:
    table_sql = lossq_safe_sql_identifier(table_name)
    column_sql = lossq_safe_sql_identifier(column_name)
    result = db.execute(
        text(f"DELETE FROM {table_sql} WHERE {column_sql} = :{value_name}"),
        {value_name: value},
    )
    return int(result.rowcount or 0)


@router.get("/")
def list_admin_users(
    current_user: User = Depends(require_admin_or_owner),
    db: Session = Depends(get_db),
):
    users = (
        db.query(User)
        .filter(User.organization_id == current_user.organization_id)
        .order_by(User.role.asc(), User.email.asc())
        .all()
    )

    return {"users": [public_user(user) for user in users]}


@router.get("/me")
def admin_me(current_user: User = Depends(get_current_user)):
    return {"user": public_user(current_user)}


@router.delete("/organizations/{organization_id}/users/{user_id}/permanent")
def permanently_delete_org_user(
    organization_id: int,
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin_or_owner),
    db: Session = Depends(get_db),
):
    # LOSSQ_ADMIN_USER_PERMANENT_DELETE_BY_ORG_AND_USER_ID_V1
    current_role = str(current_user.role or "user").strip().lower()
    current_org_id = int(current_user.organization_id or 0)

    if not current_org_id:
        raise HTTPException(status_code=403, detail="Organization access required")

    if int(organization_id) != current_org_id:
        raise HTTPException(
            status_code=403,
            detail="Admins can only permanently delete users from their own organization",
        )

    organization = db.query(Organization).filter(Organization.id == organization_id).first()
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    target_user = (
        db.query(User)
        .filter(User.id == user_id, User.organization_id == organization_id)
        .first()
    )

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found for this organization")

    target_role = str(target_user.role or "user").strip().lower()

    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot permanently delete yourself")
    if target_role == "owner":
        raise HTTPException(status_code=403, detail="Owner accounts cannot be permanently deleted here")
    if current_role == "admin" and target_role != "user":
        raise HTTPException(status_code=403, detail="Admins can only permanently delete normal users")

    deleted_user = {
        "id": target_user.id,
        "email": target_user.email,
        "role": target_user.role or "user",
        "first_name": target_user.first_name or "",
        "last_name": target_user.last_name or "",
        "organization_id": target_user.organization_id,
    }

    db.delete(target_user)
    db.commit()

    write_audit_event(
        db,
        current_user=current_user,
        action="user_permanently_deleted",
        resource_type="user",
        resource_id=str(user_id),
        details={
            "event": "user_permanently_deleted",
            "deleted_user": deleted_user,
            "organization_id": organization_id,
            "organization_name": organization.name,
            "required_identifiers": {
                "organization_id": organization_id,
                "user_id": user_id,
            },
        },
        request=request,
    )

    return {
        "message": f"{deleted_user['email']} was permanently deleted from {organization.name}.",
        "deleted_user_id": user_id,
        "organization_id": organization_id,
    }


@router.delete("/organizations/{organization_id}/users/{user_id}/account/permanent")
def permanently_delete_organization_account(
    organization_id: int,
    user_id: int,
    current_user: User = Depends(require_admin_or_owner),
    db: Session = Depends(get_db),
):
    # LOSSQ_ADMIN_ORGANIZATION_ACCOUNT_PERMANENT_DELETE_V1
    current_role = str(current_user.role or "user").strip().lower()
    current_org_id = int(current_user.organization_id or 0)

    if current_role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Owner or admin access required")

    if not current_org_id:
        raise HTTPException(status_code=403, detail="Organization access required")

    if int(organization_id) != current_org_id:
        raise HTTPException(
            status_code=403,
            detail="Owners and admins can only permanently delete their own organization account",
        )

    organization = db.query(Organization).filter(Organization.id == organization_id).first()
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    requested_user = (
        db.query(User)
        .filter(User.id == user_id, User.organization_id == organization_id)
        .first()
    )
    if not requested_user:
        raise HTTPException(
            status_code=404,
            detail="User ID was not found inside this organization account",
        )

    organization_name = organization.name or f"Organization {organization_id}"

    inspector = inspect(db.bind)
    deleted_counts = {}

    try:
        for table_name in inspector.get_table_names():
            if table_name in {"organizations", "users"}:
                continue

            columns = {column["name"] for column in inspector.get_columns(table_name)}
            if "organization_id" not in columns:
                continue

            deleted_counts[table_name] = lossq_delete_rows_by_column(
                db,
                table_name,
                "organization_id",
                "organization_id",
                organization_id,
            )

        deleted_counts["users"] = lossq_delete_rows_by_column(
            db,
            "users",
            "organization_id",
            "organization_id",
            organization_id,
        )
        deleted_counts["organizations"] = lossq_delete_rows_by_column(
            db,
            "organizations",
            "id",
            "organization_id",
            organization_id,
        )

        if deleted_counts["users"] < 1 or deleted_counts["organizations"] != 1:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail="Organization account deletion did not remove the required user and organization records",
            )

        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Permanent organization account deletion failed: {exc}",
        ) from exc

    return {
        "message": f"{organization_name} was permanently deleted.",
        "organization_id": organization_id,
        "deleted_counts": deleted_counts,
    }
