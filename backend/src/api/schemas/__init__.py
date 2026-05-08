from pydantic import BaseModel


class CancelResponse(BaseModel):
    """Response returned by any ``POST /{resource}/{id}/cancel`` endpoint."""

    id: str
    status: str
    message: str = ""
