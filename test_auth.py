import asyncio
from backend.database import get_db, async_session, engine
from backend.models import User
from backend.auth import hash_password, verify_password
from sqlalchemy import select

async def test():
    async with async_session() as session:
        # Create a user
        pwd = "mypassword123"
        hashed = hash_password(pwd)
        u = User(username="testuser", email="test@test.com", hashed_password=hashed)
        session.add(u)
        await session.commit()

        # Try to verify
        res = await session.execute(select(User).where(User.username=="testuser"))
        u_db = res.scalar_one()
        
        print(f"Hashed: {u_db.hashed_password}")
        print(f"Verified? {verify_password(pwd, u_db.hashed_password)}")

        # Clean up
        await session.delete(u_db)
        await session.commit()

if __name__ == "__main__":
    asyncio.run(test())
