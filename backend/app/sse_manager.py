# /backend/app/sse_manager.py
# NEW FILE
# Version: 1.0.0

import asyncio
from typing import Dict, Deque, Any
from collections import deque
import logging
import uuid
import json

logger = logging.getLogger(__name__)

class SSEManager:
    """
    Quản lý các kết nối Server-Sent Events (SSE) đang hoạt động.
    """
    def __init__(self):
        # Dùng dictionary để lưu các hàng đợi (queue) cho mỗi người dùng.
        # Key: user_id (str), Value: Deque[str] (hàng đợi tin nhắn dạng JSON string)
        self.active_connections: Dict[str, Deque[str]] = {}
        # Dùng asyncio.Event để thông báo cho các coroutine đang chờ.
        # Key: user_id (str), Value: asyncio.Event
        self.events: Dict[str, asyncio.Event] = {}

    async def add_connection(self, user_id: uuid.UUID) -> Deque[str]:
        """Thêm một kết nối mới cho người dùng và trả về queue của họ."""
        user_id_str = str(user_id)
        if user_id_str not in self.active_connections:
            self.active_connections[user_id_str] = deque()
            self.events[user_id_str] = asyncio.Event()
            logger.info(f"SSE connection queue created for user {user_id_str}")
        return self.active_connections[user_id_str]

    def remove_connection(self, user_id: uuid.UUID):
        """Xóa kết nối của người dùng khi họ ngắt kết nối."""
        user_id_str = str(user_id)
        if user_id_str in self.active_connections:
            # Không xóa hoàn toàn để tránh race condition, chỉ dọn dẹp event
            # Một coroutine có thể vẫn đang giữ tham chiếu đến queue
            if user_id_str in self.events:
                 self.events[user_id_str].set() # Wake up any waiting generator to let it exit
                 del self.events[user_id_str]
            del self.active_connections[user_id_str]
            logger.info(f"SSE connection queue removed for user {user_id_str}")

    async def send_message(self, user_id: uuid.UUID, message_data: Dict[str, Any]):
        """
        Chuyển đổi tin nhắn thành JSON string, thêm vào hàng đợi của người dùng 
        và kích hoạt event.
        """
        user_id_str = str(user_id)
        if user_id_str in self.active_connections:
            # Chuyển đổi dict thành JSON string trước khi đưa vào queue
            json_message = json.dumps(message_data)
            self.active_connections[user_id_str].append(json_message)
            # Kích hoạt (set) event để coroutine đang chờ biết có tin nhắn mới
            self.events[user_id_str].set()
            logger.info(f"Sent message to user {user_id_str}'s queue.")

    async def message_generator(self, user_id: uuid.UUID, request):
        """
        Một generator để lắng nghe và trả về tin nhắn cho một kết nối SSE.
        """
        user_id_str = str(user_id)
        queue = self.active_connections.get(user_id_str)
        event = self.events.get(user_id_str)

        if queue is None or event is None:
            logger.warning(f"Generator started for non-existent user {user_id_str}")
            return

        try:
            while True:
                # Kiểm tra nếu client đã ngắt kết nối
                if await request.is_disconnected():
                    logger.info(f"Client for user {user_id_str} disconnected from generator.")
                    break
                
                # Nếu có tin nhắn trong hàng đợi, gửi đi ngay
                if queue:
                    message = queue.popleft()
                    # Định dạng message theo chuẩn SSE: "data: <json_string>\n\n"
                    yield f"data: {message}\n\n"
                else:
                    # Nếu không, chờ cho đến khi event được kích hoạt (bởi send_message)
                    # hoặc chờ một khoảng timeout ngắn để kiểm tra lại is_disconnected
                    try:
                        await asyncio.wait_for(event.wait(), timeout=15)
                    except asyncio.TimeoutError:
                        # Gửi một comment để giữ kết nối sống (keep-alive)
                        yield ": keep-alive\n\n"
                        continue
                    finally:
                        # Sau khi được kích hoạt hoặc timeout, xóa cờ event 
                        # để nó có thể chờ lại ở lần sau
                        event.clear()
        finally:
            self.remove_connection(user_id)


# Tạo một instance duy nhất để sử dụng trong toàn bộ ứng dụng
sse_manager = SSEManager()