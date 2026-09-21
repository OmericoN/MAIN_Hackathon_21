import asyncio
import os

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"].replace(
    "postgresql://",
    "postgresql+asyncpg://",
    1,
)

engine = create_async_engine(DATABASE_URL)


async def test_connection():
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            print("Database connected successfully:", result.scalar())
    except Exception as e:
        print("Database connection failed:")
        print(e)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_connection())
