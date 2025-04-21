from typing import Optional

import requests
from requests import Session, Response


class MastrWebException(Exception):
    def __init__(self, message, cause=None):
        super().__init__(message)
        self.cause = cause


class MastrHTTPQueryException(MastrWebException):
    pass


class RESTClient:
    def __init__(self):
        self.session = Session()

    def query_get(self, url: str) -> str:
        r = self.session.get(url)

        if r.status_code != 200:
            raise MastrHTTPQueryException(
                f"Error while GET data from url {url}. HTTP-STATUS: {r.status_code} BODY:{r.text}"
            )
        return r.text

    def __query_head(self, url: str) -> Response:
        r = self.session.head(url, headers={"Accept-Encoding": "bytes"})

        if r.status_code != 200:
            raise MastrHTTPQueryException(
                f"Error while HEAD data from url {url}. HTTP-STATUS: {r.status_code} BODY:{r.text}"
            )
        return r

    def get_file_size_mib(self, url: str) -> Optional[float]:
        try:
            r = self.__query_head(url)
            length = int(r.headers["content-length"])
        except Exception:
            return None
        return length / (1024**2)
