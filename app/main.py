import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path

import xmltodict
from loguru import logger
from pydantic import BaseModel, Field, Json

# TODO: no as_result, only as_async_result
from result import Err, Ok, as_async_result, as_result

from app.db import DATA_DIR, ConnectionManager, Model
from app.schema import SuiteReport


@as_result(Exception)
def parse_pytest_junit_xml(file_path: Path) -> SuiteReport:
    with file_path.open() as f:
        data = xmltodict.parse(f.read())

    testsuite = data["testsuites"]["testsuite"]

    return SuiteReport(**testsuite)


connection = ConnectionManager(":memory:")


class Report(BaseModel, Model):
    path: Path
    created_at: datetime = Field(default_factory=datetime.now)
    data: Json


async def create_db():
    await connection.load_schema(Report)


@as_async_result(Exception)
async def store_report(report: SuiteReport) -> None:
    data = report.model_dump_json()
    hash_obj = hashlib.sha1(data.encode()).hexdigest()
    path_dir = DATA_DIR / hash_obj[0] / hash_obj[1]
    path_dir.mkdir(parents=True, exist_ok=True)
    path = path_dir / hash_obj[2:]
    if path.exists():
        msg = f"Atteempting to overwrite file at {path}. Aborting..."
        raise ValueError(msg)
    with path.open("w") as f:
        f.write(data)

    async with connection.session() as session:
        new_entry = Report(path=path, data=data)
        # TODO: handle case when this failed after the data file was created
        await session.add(new_entry)
        await session.commit()


async def store_new_report():
    input_path = Path("./path")
    report_result = await parse_pytest_junit_xml(input_path).and_then_async(
        store_report
    )

    match report_result:
        case Ok(_):
            logger.info("Successfully stored report")
        case Err(err):
            logger.error("something failed: {}", err)


async def print_all_reports():
    async with connection.session() as session:
        reports = await session.select_all(Report)

    for report in reports:
        raw_report = json.load(report.path.open())
        test_result = SuiteReport.model_construct(**raw_report)
        logger.info(test_result)


def main():
    asyncio.run(create_db())
    asyncio.run(store_new_report())
    asyncio.run(print_all_reports())


if __name__ == "__main__":
    main()
