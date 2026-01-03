from fastapi import Request, Response
import requests
from engine.config import AUTH_BACKEND_URL

async def django_fallback(request: Request) -> Response:
    """
    GLOBAL FALLBACK:
    Any unknown /auth/* route is forwarded to Django backend.
    """

    path = request.url.path
    query = request.url.query

    url = f"{AUTH_BACKEND_URL}{path}"
    if query:
        url = f"{url}?{query}"

    headers = {}
    for k, v in request.headers.items():
        if k.lower() in ["authorization", "content-type"]:
            headers[k] = v

    try:
        if request.method == "GET":
            r = requests.get(url, headers=headers, timeout=10)

        elif request.method == "POST":
            body = await request.body()
            r = requests.post(url, data=body, headers=headers, timeout=10)

        elif request.method == "PUT":
            body = await request.body()
            r = requests.put(url, data=body, headers=headers, timeout=10)

        elif request.method == "DELETE":
            r = requests.delete(url, headers=headers, timeout=10)

        else:
            return Response(
                content=b'{"detail":"Method not supported"}',
                status_code=405,
                media_type="application/json"
            )

        return Response(
            content=r.content,
            status_code=r.status_code,
            media_type=r.headers.get("content-type", "application/json")
        )

    except Exception as e:
        return Response(
            content=f'{{"detail":"Django proxy failed","error":"{str(e)}"}}'.encode(),
            status_code=502,
            media_type="application/json"
        )

