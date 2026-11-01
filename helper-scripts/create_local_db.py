from __future__ import annotations

import asyncio

import asyncpg


async def main() -> None:
    host = "localhost"
    port = 5432
    user = "postgres"
    password = "postgres"
    target_db = "email_replier"

    conn = await asyncpg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database="postgres",
    )
    try:
        exists = await conn.fetchval("select 1 from pg_database where datname=$1", target_db)
        if not exists:
            await conn.execute(f'create database "{target_db}"')
            print(f"created {target_db}")
        else:
            print(f"{target_db} exists")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

