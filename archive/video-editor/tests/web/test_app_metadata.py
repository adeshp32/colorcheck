from starlette.requests import Request
from starlette.responses import Response

from colorcheck.web.app import _secure_response, robots


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "scheme": "https",
            "server": ("colorcheck.example", 443),
            "client": ("127.0.0.1", 1234),
        }
    )


def test_public_pages_are_not_search_indexed() -> None:
    response = _secure_response(Response(), _request("/"))

    assert response.headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"


def test_robots_disallows_crawling() -> None:
    response = _secure_response(robots(), _request("/robots.txt"))

    assert response.status_code == 200
    assert response.body == b"User-agent: *\nDisallow: /\n"
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"
