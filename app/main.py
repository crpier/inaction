import hashlib
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast

import xmltodict
from loguru import logger
from pydantic import BaseModel, Field, model_validator
from result import Err, Ok, as_result
from sqlalchemy.engine import Dialect, Engine
from sqlalchemy.types import TEXT, TypeDecorator
from sqlmodel import Field as SQLField
from sqlmodel import Session, SQLModel, create_engine, select

DATA_DIR = Path("./data")


# TODO: annotate this as final
class TestResult(BaseModel):
    name: str = Field(alias="@name")
    full_name: str = Field(alias="@classname")
    time: float = Field(alias="@time")

    @model_validator(mode="before")
    @classmethod
    def set_result(cls, value: dict):
        if (skipped_field := value.get("skipped")) is not None:
            if skipped_field.get("@type") == "pytest.xfail":
                value["result"] = "xfail"
            else:
                value["result"] = "skipped"
        elif (_ := value.get("failure")) is not None:
            value["result"] = "fail"
        elif (
            value.get("properties") is not None
            and (properties := value.get("properties", {}).get("property")) is not None
        ):
            if isinstance(properties, list):
                for property in properties:
                    if (
                        property.get("@name") == "xfail"
                        and property.get("@value") == "True"
                    ):
                        value["result"] = "xpass"
                        break
            elif isinstance(properties, dict):
                if (
                    properties.get("@name") == "xfail"
                    and properties.get("@value") == "True"
                ):
                    value["result"] = "xpass"

            else:
                raise ValueError("what's going on here?")

        return value

    result: Literal[
        "pass",
        "fail",
        "error",
        "xfail",
        "xpass",
        "skipped",
    ] = Field(default="pass", validate_default=True)


class SuiteReport(BaseModel):
    total_tests: int = Field(alias="@tests")
    errors: int = Field(alias="@errors")
    failures: int = Field(alias="@failures")
    skipped: int = Field(alias="@skipped")
    duration: float = Field(alias="@time")
    start_time: datetime = Field(alias="@timestamp")

    tests: list[TestResult] = Field(alias="testcase")


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
    # path: Path = mapped_column(PathType)
    created_at: datetime = SQLField(default_factory=datetime.now)
    # created_at: datetime = mapped_column(default=datetime.now)


@lru_cache
def get_db_engine() -> Engine:
    engine = create_engine("sqlite:///dev.db")
    SQLModel.metadata.create_all(engine)
    return engine


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
