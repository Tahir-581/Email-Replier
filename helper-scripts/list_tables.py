from __future__ import annotations

import asyncio

import asyncpg


async def main() -> None:
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="postgres",
        database="email_replier",
    )
    try:
        db = await conn.fetchval("select current_database()")
        sch = await conn.fetchval("select current_schema()")
        print({"database": db, "schema": sch})
        rows = await conn.fetch(
            "select table_name from information_schema.tables where table_schema='public' order by table_name"
        )
        print([r["table_name"] for r in rows])
        rels = await conn.fetch(
            "select n.nspname as schema, c.relname as name, c.relkind as kind "
            "from pg_class c join pg_namespace n on n.oid=c.relnamespace "
            "where c.relname in ('emails','logs','alembic_version')"
        )
        print([dict(r) for r in rels])
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

