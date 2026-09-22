import asyncio
import httpx

async def test_flow():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Register
        pwd = "mypassword123"
        print("Registering...")
        res = await client.post("/api/auth/register", json={
            "username": "testflowuser",
            "email": "testflow@example.com",
            "password": pwd
        })
        print(f"Register status: {res.status_code}")
        print(res.text)

        # Login
        print("Logging in...")
        res = await client.post("/api/auth/login", json={
            "email": "testflow@example.com",
            "password": pwd
        })
        print(f"Login status: {res.status_code}")
        print(res.text)

if __name__ == "__main__":
    asyncio.run(test_flow())
