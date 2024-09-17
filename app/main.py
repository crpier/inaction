import hashlib
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import xmltodict
from loguru import logger
from result import Err, Ok, as_result

from app.schema import SuiteReport
from app.db import DATA_DIR


@as_result(Exception)
def parse_pytest_junit_xml(file_path: Path) -> SuiteReport:
    with file_path.open() as f:
        data = xmltodict.parse(f.read())

    testsuite = data["testsuites"]["testsuite"]

    return SuiteReport(**testsuite)


class PathType(TypeDecorator):
    impl = TEXT

    def process_bind_param(self, value: Any, _: Dialect):  # type: ignore
        if isinstance(value, Path):
            return str(value)
        return value

    def process_result_value(self, value: str | None, _: Dialect):  # type: ignore
        if value is not None:
            return Path(value)
        return value


class Report(SQLModel, table=True):
    id: int | None = SQLField(default=None, primary_key=True)
    path: Path = SQLField(sa_type=PathType)
    created_at: datetime = SQLField(default_factory=datetime.now)


@as_result(Exception)
def store_report(report: SuiteReport) -> None:
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

    engine = get_db_engine()
    with Session(engine) as session:
        new_entry = Report(path=path)
        # TODO: handle case when this failed after the data file was created
        session.add(new_entry)
        session.commit()
        session.close()


def store_new_report():
    input_path = Path("./path")
    report_result = parse_pytest_junit_xml(input_path).and_then(store_report)

    match report_result:
        case Ok(_):
            logger.info("Successfully stored report")
        case Err(err):
            logger.error("something failed: {}", err)


def print_first_report():
    engine = get_db_engine()
    with Session(engine) as session:
        report = cast(Report, session.exec(select(Report)).one())

    raw_report = json.load(report.path.open())
    test_result = SuiteReport.model_construct(**raw_report)
    logger.info(test_result)


def main():
    store_new_report()
    print_first_report()


if __name__ == "__main__":
    main()
