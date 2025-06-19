# /backend/app/routers/sse_router.py
# Version: 1.3

import logging
import uuid
from fastapi import APIRouter, Depends, Request, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from ..core.security import get_user_from_token
from ..sse_manager import sse_manager
from ..db.database import get_db_session

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/sse/notifications", summary="Establish an SSE connection for real-time notifications")
async def sse_notifications(
    request: Request,
    token: str, # FastAPI sẽ tự động lấy token từ query param
    db = Depends(get_db_session)
):
    """
    Endpoint để client kết nối SSE.
    Xác thực người dùng bằng token trong query parameter.
    """
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is missing")

    try:
        # Xác thực token để lấy thông tin user
        user = await get_user_from_token(token=token, db=db)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

        user_id = user.id
        logger.info(f"User {user.email} (ID: {user_id}) attempting to connect to SSE.")

        # Thêm kết nối vào manager và lấy message generator
        await sse_manager.add_connection(user_id)
        generator = sse_manager.message_generator(user_id, request)

        return EventSourceResponse(generator)

    except HTTPException as http_exc:
        # Forward HTTP exceptions
        raise http_exc
    except Exception as e:
        logger.error(f"Error establishing SSE connection: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not establish SSE connection")