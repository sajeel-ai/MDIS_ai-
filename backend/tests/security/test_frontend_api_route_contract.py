"""Keep frontend API path templates aligned with registered FastAPI routes."""
from pathlib import Path
import re

from fastapi.routing import APIRoute

from app.main import app


API_SOURCE = Path(__file__).resolve().parents[3] / "src" / "services" / "api.ts"


def _first_argument(source: str, start: int) -> str:
    depth = 0
    quote = None
    escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                return source[start:index].strip()
            depth -= 1
        elif char == "," and depth == 0:
            return source[start:index].strip()
    return source[start:].strip()


def _path_template(expression: str) -> str | None:
    expression = expression.strip()
    if expression.startswith("`"):
        template = expression[1:expression.rfind("`")]
        template = re.sub(r"\$\{(?:qs|params)}$", "", template)
        return re.sub(r"\$\{[^}]+}", "{param}", template)
    parts = re.split(r"\s*\+\s*", expression)
    rendered = []
    for part in parts:
        part = part.strip()
        if len(part) >= 2 and part[0] in "'\"" and part[-1] == part[0]:
            rendered.append(part[1:-1])
        elif part:
            rendered.append("{param}")
    path = "".join(rendered)
    return path if path.startswith("/") else None


def test_every_frontend_api_fetch_path_matches_a_backend_route():
    source = API_SOURCE.read_text(encoding="utf-8")
    paths = []
    marker = "apiFetch("
    offset = 0
    while (position := source.find(marker, offset)) >= 0:
        start = position + len(marker)
        expression = _first_argument(source, start)
        path = _path_template(expression)
        if path:
            paths.append(path.split("?", 1)[0])
        offset = start

    route_paths = {
        route.path.removeprefix("/api/v1") or "/"
        for route in app.routes if isinstance(route, APIRoute)
    }
    missing = []
    for path in paths:
        pattern = re.escape(path)
        pattern = re.sub(r"\\\{param\\\}", r"[^/]+", pattern)
        if not any(re.fullmatch(pattern, route_path) for route_path in route_paths):
            missing.append(path)
    assert paths, "No API paths were extracted from src/services/api.ts"
    assert missing == []
