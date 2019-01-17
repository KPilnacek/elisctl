import json
import re
from functools import partial
from traceback import print_tb
from typing import List

import pytest
from requests import Request

from tests.conftest import API_URL, TOKEN
from tools.schema.upload import upload_command

DATA = """\
1;abc
2;cde
3;fgh\
"""
USERNAME = "something"
PASSWORD = "secret"
SCHEMA_NAME = "schema.json"
schema_content: List = []
schema_id = "1"


@pytest.mark.runner_setup(
    env={"ADMIN_API_URL": API_URL, "ADMIN_API_LOGIN": USERNAME, "ADMIN_API_PASSWORD": PASSWORD}
)
class TestUpload:
    def test_schema_create(
        self, mock_login_request, mock_get_schema, requests_mock, isolated_cli_runner
    ):
        new_schema = {"content": schema_content, "name": "test"}
        new_schema_id = "2"
        schemas_url = f"{API_URL}/v1/schemas"
        new_schema_url = f"{schemas_url}/{new_schema_id}"

        requests_mock.post(
            schemas_url,
            json={"url": new_schema_url, "queues": [], **new_schema},
            additional_matcher=partial(_match_uploaded_json, new_schema),
            request_headers={"Authorization": f"Token {TOKEN}"},
            status_code=201,
        )
        requests_mock.patch(
            re.compile(fr"{API_URL}/v1/queues/\d"),
            request_headers={"Authorization": f"Token {TOKEN}"},
            additional_matcher=partial(_match_uploaded_json, {"schema": new_schema_url}),
        )

        with open(SCHEMA_NAME, "w") as schema:
            json.dump(schema_content, schema)
        result = isolated_cli_runner.invoke(upload_command, [schema_id, SCHEMA_NAME])
        assert not result.exit_code, print_tb(result.exc_info[2])

    def test_schema_rewrite(self, mock_login_request, requests_mock, isolated_cli_runner):
        schemas_url = f"{API_URL}/v1/schemas"
        schema_url = f"{schemas_url}/{schema_id}"

        requests_mock.patch(
            schema_url,
            additional_matcher=partial(_match_uploaded_json, {"content": schema_content}),
            request_headers={"Authorization": f"Token {TOKEN}"},
        )
        with open(SCHEMA_NAME, "w") as schema:
            json.dump(schema_content, schema)
        result = isolated_cli_runner.invoke(upload_command, [schema_id, SCHEMA_NAME, "--rewrite"])
        assert not result.exit_code, print_tb(result.exc_info[2])


def _match_uploaded_json(uploaded_json: dict, request: Request) -> bool:
    return request.json() == uploaded_json