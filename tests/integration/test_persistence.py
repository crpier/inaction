from pathlib import Path

from aiosqlite import Row
from pydantic import BaseModel
from snek.snektest.runner import fixture_async, load_fixture_async, test_async

from app.db import ConnectionManager


class TestModel(BaseModel):
    rowid: int | None = None
    power_level: int
    name: str
    location: Path


@fixture_async()
async def init_connection():
    conn = ConnectionManager(":memory:")
    yield conn
    await conn.close_connections()


@fixture_async()
async def load_schema():
    connection = await load_fixture_async(init_connection)

    await connection.load_schema(TestModel)
    yield


@test_async()
async def test_simple_table_is_created():
    connection = await load_fixture_async(init_connection)

    await connection.load_schema(TestModel)

    results = []
    async with connection.session() as s:
        async with s.execute("SELECT sql FROM sqlite_master;") as cursor:
            async for row in cursor:
                results.append(row["sql"])

    assert len(results) > 0, "Suite report table not created"
    assert len(results) == 1, "Multiple tables created"

    result = results[0]
    expected = """
CREATE TABLE test_model (
power_level INTEGER,
name TEXT,
location TEXT
)""".lstrip()  # lstrip the starting newline, which I added to make the test more readable
    assert result == expected, f"\n{result} !=\n{expected}"


@test_async()
async def test_inserts_are_persisted():
    connection = await load_fixture_async(init_connection)
    await load_fixture_async(load_schema)

    obj_to_add = TestModel(power_level=1, name="test", location=Path("some/path"))
    async with connection.session() as s:
        await s.add(obj_to_add)
        await s.commit()

    results: list[Row] = []
    async with connection.session() as s:
        async with s.execute("SELECT * FROM test_model") as cursor:
            async for row in cursor:
                results.append(row)

    assert len(results) == 1

    result = results[0]
    assert result.keys() == ["power_level", "name", "location"]
    assert result["power_level"] == 1
    assert result["name"] == "test"
    assert result["location"] == "some/path"


@test_async()
async def test_select_from_table():
    connection = await load_fixture_async(init_connection)
    await load_fixture_async(load_schema)

    added_obj = TestModel(power_level=1, name="test", location=Path("some/path"))
    async with connection.session() as s:
        await s.add(added_obj)
        await s.commit()

    async with connection.session() as s:
        results = await s.select_all(TestModel)

    assert len(results) == 1

    result = results[0]
    assert result.power_level == added_obj.power_level
    assert result.name == added_obj.name
    assert result.location == Path("some/path")
    assert result.rowid == 1


@test_async()
async def test_insert_list():
    connection = await load_fixture_async(init_connection)
    await load_fixture_async(load_schema)

    added_objects = [
        TestModel(power_level=i, name="test", location=Path("some/path"))
        for i in range(1, 11)
    ]
    async with connection.session() as s:
        await s.add(added_objects)
        await s.commit()

    async with connection.session() as s:
        i = 0
        async for result in s.select(TestModel):
            i += 1
            assert result == TestModel(
                power_level=i, name="test", rowid=i, location=Path("some/path")
            )


@test_async()
async def test_select_generator():
    connection = await load_fixture_async(init_connection)
    await load_fixture_async(load_schema)

    added_objects = [
        TestModel(power_level=i, name="test", location=Path("some/path"))
        for i in range(1, 11)
    ]
    async with connection.session() as s:
        for obj in added_objects:
            await s.add(obj)
        await s.commit()

    async with connection.session() as s:
        i = 0
        async for result in s.select(TestModel):
            i += 1
            assert result == TestModel(
                power_level=i, name="test", rowid=i, location=Path("some/path")
            )
