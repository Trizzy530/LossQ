from fastapi import APIRouter

router = APIRouter(prefix="/policies", tags=["Policies"])

@router.get("/")
def get_policies():
    return [
        {
            "id": 1,
            "account_id": 1,
            "carrier_name": "Progressive",
            "policy_number": "POL123456",
            "line_of_business": "Commercial Auto",
            "status": "active"
        }
    ]