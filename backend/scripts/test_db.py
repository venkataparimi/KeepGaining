import asyncio
import asyncpg

async def test_connection():
    try:
        conn = await asyncpg.connect('postgresql://user:password@127.0.0.1:5432/keepgaining')
        print("SUCCESS: Database connection working!")
        await conn.close()
        return True
    except Exception as e:
        print(f"FAILED: Connection error - {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_connection())
