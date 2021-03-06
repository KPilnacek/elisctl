from traceback import print_tb

import pytest
import re

from elisctl.csv import download_command as download_csv

DATA = """\
1;abc
2;cde
3;fgh\
"""
USERNAME = "something"
PASSWORD = "secret"
CSV_URL = "mock://csv.example.com"


class TestDownload:
    @pytest.mark.runner_setup(
        env={"ELIS_URL": CSV_URL, "ELIS_USERNAME": USERNAME, "ELIS_PASSWORD": PASSWORD}
    )
    def test_csv(self, requests_mock, cli_runner):
        requests_mock.get(re.compile(fr"{CSV_URL}/byperiod/\d+/\d{{10}}"), text=DATA)
        result = cli_runner.invoke(download_csv, ["--step", "1"])
        assert not result.exit_code, print_tb(result.exc_info[2])
        assert 1 == len(requests_mock.request_history)
        assert DATA == result.stdout.strip()
