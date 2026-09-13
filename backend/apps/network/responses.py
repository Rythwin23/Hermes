from collections.abc import Mapping
from gzip import compress
from typing import Any

import ormsgpack
from django.http import HttpRequest, HttpResponse, JsonResponse


MESSAGEPACK_MIME_TYPE = "application/msgpack"


def api_response(request: HttpRequest, payload: Mapping[str, Any]) -> HttpResponse:
    """Return MessagePack when requested, otherwise preserve the JSON API."""
    if MESSAGEPACK_MIME_TYPE in request.headers.get("Accept", ""):
        body = ormsgpack.packb(payload)
        accepts_gzip = "gzip" in request.headers.get("Accept-Encoding", "")
        if accepts_gzip:
            body = compress(body)

        response = HttpResponse(body, content_type=MESSAGEPACK_MIME_TYPE)
        response["Vary"] = "Accept, Accept-Encoding"
        if accepts_gzip:
            response["Content-Encoding"] = "gzip"
        return response

    return JsonResponse(payload)