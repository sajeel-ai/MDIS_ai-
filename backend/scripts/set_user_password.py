"""Provision or change a user's password without placing it in shell history."""

import argparse
import asyncio
from getpass import getpass

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models import User
from app.security.auth import hash_password


async def set_password(email: str, password: str) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email.strip().lower()))
        user = result.scalars().first()
        if user is None:
            return False
        user.password_hash = hash_password(password)
        await session.commit()
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email", help="Existing account email")
    args = parser.parse_args()

    password = getpass("New password (minimum 12 characters): ")
    confirmation = getpass("Confirm password: ")
    if len(password) < 12:
        parser.error("Password must be at least 12 characters")
    if password != confirmation:
        parser.error("Passwords do not match")
    if not asyncio.run(set_password(args.email, password)):
        parser.error("No account exists with that email")
    print(f"Password updated for {args.email.strip().lower()}")


if __name__ == "__main__":
    main()
