from pydantic import BaseModel
from typing import Optional

class Policy(BaseModel):
    id: int
    account_id: int
    carrier_name: str
    policy_number: str
    line_of_business: str
    status: Optional[str] = "active"