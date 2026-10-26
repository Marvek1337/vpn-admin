import asyncio

from app.database import SessionLocal
from app.services.cleanup import cleanup_expired_clients


async def main():
    db = SessionLocal()
    try:
        result = await cleanup_expired_clients(db)
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
