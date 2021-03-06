import secrets
import string
from platform import platform
from contextlib import AbstractContextManager

import click
import requests
from requests import Response
from typing import Dict, List, Tuple, Optional, Iterable, Any, Union

from elisctl import __version__
from elisctl.configure import get_credential
from . import ORGANIZATIONS, APIObject, WORKSPACES, QUEUES, SCHEMAS, CONNECTORS

HEADERS = {"User-Agent": f"elisctl/{__version__} ({platform()})"}


class APIClient(AbstractContextManager):
    def __init__(
        self,
        url: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        use_api_version: bool = True,
        auth_using_token: bool = True,
        profile: Optional[str] = None
    ):
        self._url = url
        self._user = user
        self._password = password
        self._use_api_version = use_api_version
        self._auth_using_token = auth_using_token
        self._profile = profile

        self.token: Optional[str] = None

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.logout()

    @classmethod
    def csv(cls, url: str = None, user: str = None, password: str = None, profile: str = None) -> "APIClient":
        return cls(url, user, password, False, False, profile)

    @property
    def user(self) -> str:
        if self._user is None:
            self._user = get_credential("username", self._profile)
        return self._user

    @property
    def password(self) -> str:
        if self._password is None:
            self._password = get_credential("password", self._profile)
        return self._password

    @property
    def url(self) -> str:
        if self._url is None:
            _url = get_credential("url", self._profile).rstrip("/")
            self._url = f'{_url}{"/v1" if self._use_api_version else ""}'
        return self._url

    def get_token(self) -> str:
        # self.post cannot be used as it is dependent on self.get_token().
        response = requests.post(
            f"{self.url}/auth/login",
            json={"username": self.user, "password": self.password},
            headers=HEADERS,
        )
        if response.status_code == 401:
            raise click.ClickException(f"Login failed with the provided credentials.")
        elif not response.ok:
            raise click.ClickException(f"Invalid response [{response.url}]: {response.text}")

        return response.json()["key"]

    def post(
        self, path: Union[str, APIObject], data: dict, expected_status_code: int = 201
    ) -> Response:
        return self._request_url(
            "post", f"{self.url}/{path}", json=data, expected_status_code=expected_status_code
        )

    def patch(self, path: Union[str, APIObject], data: dict) -> Response:
        return self._request_url("patch", f"{self.url}/{path}", json=data)

    def get(self, path: Union[str, APIObject], query: dict = None) -> Response:
        return self._request_url("get", f"{self.url}/{path}", query)

    def get_url(self, url: str, query: dict = None) -> Response:
        return self._request_url("get", url, query)

    def delete_url(self, url: str) -> Response:
        return self._request_url("delete", url, expected_status_code=204)

    def _request_url(
        self, method: str, url: str, query: dict = None, expected_status_code: int = 200, **kwargs
    ) -> Response:
        auth = self._authentication
        headers = {**HEADERS, **auth.pop("headers", {}), **kwargs.pop("headers", {})}

        response = requests.request(
            method, url, params=_encode_booleans(query), headers=headers, **auth, **kwargs
        )
        if response.status_code != expected_status_code:
            raise click.ClickException(f"Invalid response [{response.url}]: {response.text}")
        return response

    def delete(self, to_delete: Dict[str, str], verbose: int = 0, item: str = "annotation") -> None:
        for id_, url in to_delete.items():
            try:
                self.delete_url(url)
            except click.ClickException as exc:
                click.echo(f'Deleting {item} {id_} caused "{exc}".')
            except Exception as exc:
                click.echo(f'Deleting {item} {id_} caused an unexpected exception: "{exc}".')
                raise click.ClickException(str(exc))
            else:
                if verbose > 1:
                    click.echo(f"Deleted {item} {id_}.")

    def get_paginated(
        self,
        path: Union[str, APIObject],
        query: Optional[Dict[str, Any]] = None,
        *,
        key: str = "results",
    ) -> Tuple[List[Dict[str, Any]], int]:
        response = self.get(path, query)
        response_dict = response.json()

        res = response_dict[key]
        next_page = response_dict["pagination"]["next"]

        while next_page:
            response = self.get_url(next_page)
            response_dict = response.json()

            res.extend(response_dict[key])
            next_page = response_dict["pagination"]["next"]

        return res, response_dict["pagination"]["total"]

    def _sideload(
        self, objects: List[dict], sideloads: Optional[Iterable[APIObject]] = None
    ) -> List[dict]:
        for sideload in sideloads or []:
            sideloaded, _ = self.get_paginated(sideload)
            sideloaded_dicts = {
                sideloaded_dict["url"]: sideloaded_dict for sideloaded_dict in sideloaded
            }

            def inject_sideloaded(obj: dict) -> dict:
                try:
                    url = obj[sideload.singular]
                except KeyError:
                    obj[sideload.plural] = [
                        sideloaded_dicts.get(url, {}) for url in obj[sideload.plural]
                    ]
                else:
                    obj[sideload.singular] = sideloaded_dicts.get(url, {})
                return obj

            objects = [inject_sideloaded(o) for o in objects]
        return objects

    @property
    def _authentication(self) -> dict:
        if self._auth_using_token:
            if self.token is None:
                self.token = self.get_token()
            return {"headers": {"Authorization": "Token " + self.token}}
        else:
            return {"auth": (self.user, self.password)}

    def logout(self) -> None:
        if self._auth_using_token:
            self.post("auth/logout", {}, expected_status_code=200)


class ELISClient(APIClient):
    def get_organization(self, organization_id: Optional[int] = None) -> dict:
        if organization_id is None:
            user_details = get_json(self.get("auth/user"))
            try:
                organization_url = user_details[ORGANIZATIONS.singular]
            except KeyError:
                organization_url = get_json(self.get_url(user_details["url"]))[
                    ORGANIZATIONS.singular
                ]
            res = self.get_url(organization_url)
        else:
            res = self.get(f"{ORGANIZATIONS}/{organization_id}")
        return get_json(res)

    def get_workspaces(self, sideloads: Optional[Iterable[APIObject]] = None) -> List[dict]:
        workspaces_list, _ = self.get_paginated(WORKSPACES)
        self._sideload(workspaces_list, sideloads)
        return workspaces_list

    def get_workspace(
        self, id_: Optional[int] = None, sideloads: Optional[Iterable[APIObject]] = None
    ) -> dict:
        if id_ is None:
            try:
                [workspace] = self.get_workspaces()
            except ValueError as e:
                raise click.ClickException("Workspace ID must be specified.") from e
        else:
            workspace = get_json(self.get(f"{WORKSPACES}/{id_}"))

        self._sideload([workspace], sideloads)
        return workspace

    def get_queues(
        self, sideloads: Optional[Iterable[APIObject]] = None, workspace: Optional[int] = None
    ) -> List[dict]:
        query = {}
        if workspace:
            query[WORKSPACES.singular] = workspace
        queues_list, _ = self.get_paginated(QUEUES, query=query)
        self._sideload(queues_list, sideloads)
        return queues_list

    def get_queue(
        self, id_: Optional[int] = None, sideloads: Optional[Iterable[APIObject]] = None
    ) -> dict:
        if id_ is None:
            try:
                [queue] = self.get_queues()
            except ValueError as e:
                raise click.ClickException("Queue ID must be specified.") from e
        else:
            queue = get_json(self.get(f"{QUEUES}/{id_}"))

        self._sideload([queue], sideloads)
        return queue

    def create_schema(self, name: str, content: List[dict]) -> dict:
        return get_json(self.post(SCHEMAS, data={"name": name, "content": content}))

    def create_queue(
        self,
        name: str,
        workspace_url: str,
        schema_url: str,
        connector_url: Optional[str] = None,
        locale: Optional[str] = None,
    ) -> dict:
        data = {
            "name": name,
            "workspace": workspace_url,
            "schema": schema_url,
            # XXX: The API should provide reasonable defaults:
            "rir_url": "https://all.rir.rossum.ai",
        }
        if connector_url is not None:
            data[CONNECTORS.singular] = connector_url
        if locale is not None:
            data["locale"] = locale
        return get_json(self.post("queues", data))

    def create_inbox(self, name: str, email_prefix: str, bounce_email: str, queue_url: str) -> dict:
        alphabet = string.ascii_lowercase + string.digits
        email_suffix = "".join(secrets.choice(alphabet) for _ in range(6))
        return get_json(
            self.post(
                "inboxes",
                data={
                    "name": name,
                    "email": email_prefix + "-" + email_suffix + "@elis.rossum.ai",
                    "bounce_email_to": bounce_email,
                    "queues": [queue_url],
                },
            )
        )


def get_json(response: Response) -> dict:
    try:
        return response.json()
    except ValueError as e:
        raise click.ClickException(f"Invalid JSON [{response.url}]: {response.text}") from e


def get_text(response: Response) -> str:
    try:
        return response.text
    except ValueError as e:
        raise click.ClickException(f"Invalid text [{response.url}]: {response.text}") from e


def _encode_booleans(query: Optional[dict]) -> Optional[dict]:
    if query is None:
        return query

    def bool_to_str(b: Any) -> Any:
        if isinstance(b, bool):
            return str(b).lower()
        return b

    res = {}
    for k, vs in query.items():
        if isinstance(vs, str) or not hasattr(vs, "__iter__"):
            vs = [vs]
        res[k] = (bool_to_str(v) for v in vs)
    return res
