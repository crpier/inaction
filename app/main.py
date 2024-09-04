import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypeVar

import xmltodict
from loguru import logger
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import TEXT, TypeDecorator
from typing_extensions import TypeIs

T = TypeVar("T")

type Result[T] = T | Exception


def result_todo() -> Result[Any]:
    raise NotImplementedError


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


def parse_pytest_junit_xml(file_path: Path) -> Result[SuiteReport]:
    try:
        with file_path.open() as f:
            data = xmltodict.parse(f.read())

        testsuite = data["testsuites"]["testsuite"]

        return SuiteReport(**testsuite)
    except Exception as e:
        return e


class Base(DeclarativeBase): ...


class PathType(TypeDecorator):
    impl = TEXT

    def process_bind_param(self, value, dialect):
        """Convert Path to string before saving to the database."""
        if isinstance(value, Path):
            return str(value)
        return value

    def process_result_value(self, value, dialect):
        """Convert string back to Path after loading from the database."""
        if value is not None:
            return Path(value)
        return value


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[Path] = mapped_column(PathType)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


def store_report(report: SuiteReport) -> Result[None]:
    try:
        engine = create_engine("sqlite:///dev.db")
        Session = sessionmaker(bind=engine)
        session = Session()
        Base.metadata.create_all(engine)

        new_entry = Report(path=Path("./reports_i_guess"))
        session.add(new_entry)
        session.commit()
        session.close()
    except Exception as err:
        return err

    return None


def is_error(res: Result[Any]) -> TypeIs[Exception]:
    if isinstance(res, Exception):
        return True
    return False


input_path = Path("./path")


if is_error(result := parse_pytest_junit_xml(input_path)):
    logger.error("Couldn't take suite results: {}", result)
    sys.exit(1)

if is_error(store_result := store_report(result)):
    logger.error("Couldn't take suite results: {}", store_result)
    sys.exit(1)

logger.info("Done!")
