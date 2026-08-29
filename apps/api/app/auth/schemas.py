import re
import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    username: str
    country_code: str = Field(min_length=2, max_length=2)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not USERNAME_RE.match(v):
            raise ValueError("Usernames are 3-32 characters: letters, numbers, underscores only.")
        return v

    @field_validator("country_code")
    @classmethod
    def validate_country(cls, v: str) -> str:
        return v.upper()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    id_token: str
    # Only needed the first time a Google sign-in creates a brand-new account.
    username: str | None = None
    country_code: str | None = None


class AuthUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    is_verified: bool
    is_admin: bool

    model_config = {"from_attributes": True}
