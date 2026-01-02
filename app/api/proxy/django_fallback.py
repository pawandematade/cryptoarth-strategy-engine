from fastapi import Request, Response
import logging

logger = logging.getLogger(__name__)

async def django_fallback(request: Request) -> Response:
    """
    Django fallback DISABLED.
    FastAPI is the single backend.
    Prevents self-calling HTTPS proxy loops.
    """

    logger.warning(
        f"🚫 Django proxy disabled | path={request.url.path}"
    )

    return Response(
        content=b'{"success": true, "message": "Handled by FastAPI (Django proxy disabled)"}',
        status_code=200,
        media_type="application/json"
    )
