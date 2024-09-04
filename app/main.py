from datetime import datetime
from pprint import pprint as print
from typing import Literal

import xmltodict
from pydantic import BaseModel, Field, model_validator

data = xmltodict.parse(open("./path").read())
testsuite = data["testsuites"]["testsuite"]


# TODO: annotate this as final
class TestResult(BaseModel):
    name: str = Field(alias="@name")
    full_name: str = Field(alias="@classname")
    time: float = Field(alias="@time")

    @model_validator(mode="before")
    @classmethod
    def set_result(cls, value: dict):
        if (skipped_field := value.get("skipped")) is not None:
            if skipped_field.get("@message") == "unconditional skip":
                value["result"] = "skipped_unconditional"
            elif skipped_field.get("@type") == "pytest.xfail":
                value["result"] = "xfail"
            else:
                # TODO: how does a conditional skip look in junit
                value["result"] = "skipped_conditional"
        if (_ := value.get("failure")) is not None:
            value["result"] = "fail"
        # TOOD: xpass
        return value

    result: Literal[
        "pass",
        "fail",
        "error",
        "xfail",
        "xpass",
        "skipped_unconditional",
        "skipped_conditional",
    ] = Field(default="pass", validate_default=True)


class SuiteResult(BaseModel):
    total_tests: int = Field(alias="@tests")
    errors: int = Field(alias="@errors")
    failures: int = Field(alias="@failures")
    skipped: int = Field(alias="@skipped")
    duration: float = Field(alias="@time")
    start_time: datetime = Field(alias="@timestamp")

    tests: list[TestResult] = Field(alias="testcase")


result = SuiteResult(**testsuite)
print(result)
for case in result.tests:
    print(case)
