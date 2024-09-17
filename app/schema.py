from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.db import ConnectionManager


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

    async def save(self, connections: ConnectionManager):
        async with connections.session() as session:
            session.execute()


class SuiteReport(BaseModel):
    total_tests: int = Field(alias="@tests")
    errors: int = Field(alias="@errors")
    failures: int = Field(alias="@failures")
    skipped: int = Field(alias="@skipped")
    duration: float = Field(alias="@time")
    start_time: datetime = Field(alias="@timestamp")

    tests: list[TestResult] = Field(alias="testcase")
