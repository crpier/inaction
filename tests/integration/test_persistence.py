from snek.snektest.runner import fixture_async, load_fixture_async, test_async

from app.db import ConnectionManager
from app.schema import SuiteReport


@fixture_async()
async def init_connection():
    conn = ConnectionManager(":memory:")
    yield conn
    await conn.close_connections()


@fixture_async()
async def orm():
    connection = await load_fixture_async(init_connection)

    await connection.load_schema(SuiteReport)
    yield


@test_async()
async def test_db_is_created():
    connection = await load_fixture_async(init_connection)

    await connection.load_schema(SuiteReport)
    async with connection.session() as s:
        async with s.execute(
            "SELECT sql FROM sqlite_master where name='suite_report';"
        ) as cursor:
            fetch_result = await cursor.fetchone()
            assert fetch_result is not None, "Suite report table not created"
            result = fetch_result[0]
            expected = """CREATE TABLE suite_report (\n    id INTEGER\n)"""
            assert result == expected, f"{result} != {expected}"
