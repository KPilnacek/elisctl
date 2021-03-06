import json
from contextlib import suppress
from dataclasses import dataclass

from typing import Iterable, Iterator, Tuple, Union


def split_dict_params(
    datapoint_parameters: Iterable[str]
) -> Iterator[Tuple[str, Union[str, int, dict, None, list]]]:
    for param in datapoint_parameters:
        key, value = param.split("=", 1)
        with suppress(ValueError):
            value = json.loads(value)
        yield key, value


@dataclass(frozen=True)
class APIObject:
    NOT_SET = "NOT_SET"

    plural: str
    singular: str = NOT_SET

    def __post_init__(self) -> None:
        if self.singular is self.NOT_SET:
            # https://docs.python.org/3/library/dataclasses.html#frozen-instances
            object.__setattr__(self, "singular", self.plural.rstrip("s"))

    def __str__(self) -> str:
        return self.plural

    # todo: add list and detail methods (the base_url needs to be somehow obtained)


ORGANIZATIONS = APIObject("organizations")
WORKSPACES = APIObject("workspaces")
QUEUES = APIObject("queues")
INBOXES = APIObject("inboxes", "inbox")
CONNECTORS = APIObject("connectors")
SCHEMAS = APIObject("schemas")
USERS = APIObject("users")
