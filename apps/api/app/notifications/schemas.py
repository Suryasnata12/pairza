from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


class PushSubscriptionBase(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2048)

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()

        # Browser push endpoints should use HTTPS and a recognized
        # browser push service. This also reduces SSRF risk when the
        # backend later sends messages to saved endpoints.
        allowed = (
            host == "fcm.googleapis.com"
            or host == "updates.push.services.mozilla.com"
            or host.endswith(".push.services.mozilla.com")
            or host == "web.push.apple.com"
        )

        if parsed.scheme != "https" or not allowed:
            raise ValueError("Unsupported browser push endpoint.")

        return value


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class PushSubscriptionCreate(PushSubscriptionBase):
    keys: PushSubscriptionKeys


class PushSubscriptionDelete(PushSubscriptionBase):
    pass