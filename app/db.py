import asyncio
from pathlib import Path
from textwrap import dedent
from typing import Literal, cast

from aiosqlite import connect
from pydantic import BaseModel

from app.utils import camel_to_snake

DATA_DIR = Path("./data")

type SQLiteDSN = Path | Literal[":memory:"]


class SQLiteSession:
    def __init__(self, db_path: SQLiteDSN) -> None:
        self._session = connect(db_path)
        self._initialized = False

    async def __aenter__(self):
        if self._initialized is False:
            self._session = await self._session
            self._initialized = True
        return self._session

    # TODO: annotate and handle exceptions
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Simply commit"""
        await self._session.commit()
        pass

    async def close(self):
        await self._session.close()


class ConnectionManager:
    # TODO: support URI, too
    def __init__(self, default_db_path: SQLiteDSN) -> None:
        self._connections: dict[SQLiteDSN, SQLiteSession] = {}
        self._default_db_path = default_db_path

    def session(self, db_location: SQLiteDSN | None = None) -> SQLiteSession:
        if db_location is None:
            # TODO: any way I can avoid this cast?
            db_location = cast(SQLiteDSN, self._default_db_path)

        if db_location in self._connections:
            return self._connections[db_location]

        self._connections[db_location] = SQLiteSession(db_location)
        return self._connections[db_location]

    async def close_connections(self):
        for connection in self._connections.values():
            await connection.close()

    async def load_schema(
        self, schema: type[BaseModel], db_path: SQLiteDSN | None = None
    ):
        if db_path is None:
            # TODO: any way I can avoid this cast?
            db_path = cast(SQLiteDSN, self._default_db_path)
        stmt = self._generate_create_table_statement(schema)
        async with self.session(db_path) as s:
            await s.execute(stmt)
            await s.commit()

    def _generate_create_table_statement(self, schema: type[BaseModel]):
        table_name = camel_to_snake(schema.__name__)
        # TODO: ensure this is safe
        return dedent(f"""
            CREATE TABLE {table_name} (
                id INTEGER
            )
        """)


async def main():
    manager = ConnectionManager(default_db_path=Path("./dev.db"))
    async with manager.session(Path("./dev.db")) as db:
        await db.execute(
            "create table if not exists report (path TEXT, created_at INTEGER)"
        )
        await db.execute(
            "INSERT into report (path, created_at) values ('some/path', '2024')"
        )

    async with manager.session(Path("./dev.db")) as sess:
        async with sess.execute("SELECT * from report") as cursor:
            async for row in cursor:
                print(row)

    await manager.close_connections()
    print("on")


if __name__ == "__main__":
    asyncio.run(main())
