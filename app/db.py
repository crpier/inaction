import asyncio
from datetime import datetime
from collections.abc import AsyncGenerator, Mapping
from pathlib import Path
from typing import Annotated, Any, Final, Literal, Protocol, TypeVar, cast

import aiosqlite
from aiosqlite import connect
from pydantic import BaseModel
from pydantic.types import Json
from pydantic.fields import FieldInfo

from app.utils import camel_to_snake

DATA_DIR = Path("./data")

type SQLiteDSN = Path | Literal[":memory:"]

T = TypeVar("T", bound=BaseModel)

# TODO: query type, that has cleaner in constructor


class Model:
    rowid: int | None = None

    def __init__(self, rowid: int | None = None):
        self.rowid: Final[int | None] = rowid


python_to_sqlite_types: dict[type, type["Column"]] = {}


# TODO: make sqlite strict on startup
class Column(Protocol):
    PYTHON_TYPE: Any
    SQLITE_TYPE: Literal["INTEGER", "REAL", "TEXT", "BLOB"]

    def __init_subclass__(cls) -> None:
        python_to_sqlite_types[cls.PYTHON_TYPE] = cls
        return super().__init_subclass__()

    @staticmethod
    def to_sqlite_type(value: Any) -> str | int | float | bytes:
        raise NotImplementedError

    # Not sure you'd want this since Pydantic will handle validation
    # @staticmethod
    # def from_sqlite_type(value: str | int | float | bytes) -> Any:
    #     raise NotImplementedError


class IntegerColumn(Column):
    PYTHON_TYPE = int
    SQLITE_TYPE: Literal["INTEGER", "REAL", "TEXT", "BLOB"] = "INTEGER"

    @staticmethod
    def to_sqlite_type(value: Any) -> int:
        return value


class TextColumn(Column):
    PYTHON_TYPE = str
    SQLITE_TYPE: Literal["INTEGER", "REAL", "TEXT", "BLOB"] = "TEXT"

    @staticmethod
    def to_sqlite_type(value: Any) -> str:
        return value


class PathColumn(Column):
    PYTHON_TYPE = Path
    SQLITE_TYPE: Literal["INTEGER", "REAL", "TEXT", "BLOB"] = "TEXT"

    @staticmethod
    def to_sqlite_type(value: Path) -> str:
        return str(value)

class DateTimeColumn(Column):
    PYTHON_TYPE = datetime
    SQLITE_TYPE: Literal["INTEGER", "REAL", "TEXT", "BLOB"] = "TEXT"

    @staticmethod
    # TODO: is there any static validation I can do for the type of the value param?
    def to_sqlite_type(value: datetime) -> str:
        return value.isoformat()

class JsonColumn(Column):
    PYTHON_TYPE = Json
    SQLITE_TYPE: Literal["INTEGER", "REAL", "TEXT", "BLOB"] = "TEXT"

    @staticmethod
    def to_sqlite_type(value: Json) -> str:
        return str(value)

def model_to_insert_statement(model: BaseModel) -> tuple[str, dict[str, Any]]:
    table_name = camel_to_snake(model.__class__.__name__)
    params: dict[str, Any] = {}
    for name, field in model.model_fields.items():
        if name == "rowid":
            continue
        if field.annotation is None:
            raise NotImplementedError(
                "Fields without type annotations are not supported"
            )
        column_class = python_to_sqlite_types[field.annotation]
        raw_value = getattr(model, name)
        value = column_class.to_sqlite_type(raw_value)
        params[name] = value

    stmt = (
        f"INSERT INTO {table_name} ({', '.join([f'"{name}"' for name in params])}) "
        f"VALUES ({', '.join(f":{name}" for name in params)})"
    )
    return stmt, params


class SQLiteSession:
    def __init__(self, db_path: SQLiteDSN) -> None:
        self._session = connect(db_path)
        self._initialized = False

    async def __aenter__(self):
        if self._initialized is False:
            self._session = await self._session
            self._session.row_factory = aiosqlite.Row
            self._initialized = True
        return self

    def execute(self, sql: str, parameters: Mapping[str, Any] | None = None):
        if parameters is None:
            return self._session.execute(sql)
        return self._session.execute(sql, parameters)

    def commit(self):
        return self._session.commit()

    async def add(self, data_to_add: T | list[T]):
        if not isinstance(data_to_add, list):
            data_to_add = [data_to_add]
        for obj in data_to_add:
            stmt, params = model_to_insert_statement(obj)
            await self.execute(stmt, params)

    async def select_all(self, model: type[T]) -> list[T]:
        column_names = [name for name in model.model_fields.keys()]
        column_names.append("rowid")
        column_names = ", ".join(column_names)
        stmt = f"SELECT {column_names} FROM {camel_to_snake(model.__name__)}"
        results = []
        async with self.execute(stmt) as cursor:
            async for row in cursor:
                # When I do just **row, I get "got multiple values for keyword argument 'rowid'"
                results.append(model(**dict(row)))
        return results

    async def select(self, model: type[T]) -> AsyncGenerator[T, None]:
        column_names = [name for name in model.model_fields.keys()]
        column_names.append("rowid")
        column_names = ", ".join(column_names)
        stmt = f"SELECT {column_names} FROM {camel_to_snake(model.__name__)}"
        async with self.execute(stmt) as cursor:
            async for row in cursor:
                # When I do just **row, I get "got multiple values for keyword argument 'rowid'"
                yield model(**dict(row))

    # TODO: annotate and handle exceptions
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Simply commit"""
        await self._session.commit()

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
        create_statement = f"CREATE TABLE {table_name} (\n"
        for field_name, field in schema.model_fields.items():
            if field_name == "rowid":
                continue
            create_statement += self._get_field_create_statement(field_name, field)
        # TODO: ensure this is safe
        create_statement = create_statement.rstrip(",\n")
        create_statement += "\n)"
        return create_statement

    def _get_field_create_statement(self, field_name: str, field: FieldInfo) -> str:
        if field.annotation is None:
            raise NotImplementedError(
                "Fields without type annotations are not supported"
            )
        sqlite_type = python_to_sqlite_types[field.annotation].SQLITE_TYPE
        return f"{field_name} {sqlite_type},\n"


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
