from sqlalchemy import select

from app.auth import service as auth_service
from app.auth.schemas import RegisterRequest
from app.common.exceptions import ConflictError, UnauthorizedError
from app.common.security import hash_password, verify_password
from app.users.models import Profile, User


async def test_register_creates_user_profile_and_preferences(db):
    payload = RegisterRequest(email="newuser@test.com", password="SecurePass123!", username="new_user", country_code="us")
    user = await auth_service.register_user(db, payload)

    assert user.email == "newuser@test.com"
    assert user.hashed_password != "SecurePass123!"  # never stored raw

    profile = (await db.execute(select(Profile).where(Profile.user_id == user.id))).scalar_one()
    assert profile.username == "new_user"
    assert profile.country_code == "US"  # normalized to uppercase


async def test_duplicate_email_is_rejected(db):
    payload = RegisterRequest(email="dupe@test.com", password="SecurePass123!", username="dupe_one", country_code="US")
    await auth_service.register_user(db, payload)

    payload2 = RegisterRequest(email="dupe@test.com", password="AnotherPass123!", username="dupe_two", country_code="US")
    try:
        await auth_service.register_user(db, payload2)
        assert False, "expected ConflictError"
    except ConflictError as e:
        assert e.code == "email_taken"


async def test_duplicate_username_is_rejected(db):
    payload = RegisterRequest(email="user1@test.com", password="SecurePass123!", username="taken_name", country_code="US")
    await auth_service.register_user(db, payload)

    payload2 = RegisterRequest(email="user2@test.com", password="SecurePass123!", username="taken_name", country_code="US")
    try:
        await auth_service.register_user(db, payload2)
        assert False, "expected ConflictError"
    except ConflictError as e:
        assert e.code == "username_taken"


async def test_login_with_wrong_password_is_rejected(db):
    payload = RegisterRequest(email="loginer@test.com", password="CorrectPass123!", username="loginer", country_code="US")
    await auth_service.register_user(db, payload)

    try:
        await auth_service.authenticate_user(db, "loginer@test.com", "WrongPassword")
        assert False, "expected UnauthorizedError"
    except UnauthorizedError:
        pass


async def test_login_with_correct_password_succeeds(db):
    payload = RegisterRequest(email="loginer2@test.com", password="CorrectPass123!", username="loginer2", country_code="US")
    await auth_service.register_user(db, payload)

    user = await auth_service.authenticate_user(db, "loginer2@test.com", "CorrectPass123!")
    assert user.email == "loginer2@test.com"


async def test_nonexistent_email_gives_same_error_as_wrong_password(db):
    """Prevents user enumeration via login error messages."""
    try:
        await auth_service.authenticate_user(db, "doesnotexist@test.com", "whatever")
        assert False, "expected UnauthorizedError"
    except UnauthorizedError as e:
        assert e.code == "invalid_credentials"


async def test_password_is_hashed_with_argon2(db):
    hashed = hash_password("MyPassword123!")
    assert hashed.startswith("$argon2id$")
    assert verify_password("MyPassword123!", hashed) is True
    assert verify_password("WrongPassword", hashed) is False


async def test_token_pair_issuance_and_rotation(db):
    payload = RegisterRequest(email="rotator@test.com", password="Pass123456!", username="rotator", country_code="US")
    user = await auth_service.register_user(db, payload)

    access1, refresh1 = await auth_service.issue_token_pair(db, user)
    assert access1 and refresh1

    access2, refresh2 = await auth_service.rotate_refresh_token(db, refresh1)
    assert access2  # a fresh access token was issued
    assert refresh2 != refresh1  # the refresh token itself carries a unique jti and must differ

    # The old refresh token must be single-use — reusing it should now fail.
    try:
        await auth_service.rotate_refresh_token(db, refresh1)
        assert False, "expected UnauthorizedError on reused refresh token"
    except UnauthorizedError:
        pass
