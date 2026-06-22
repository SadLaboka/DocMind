import asyncio

from src.stream.app import app


async def main():
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
