from fastapi import FastAPI

# Khởi tạo ứng dụng FastAPI
app = FastAPI(
    title="CronPost API",
    description="API for CronPost - A service to send messages to the future.",
    version="0.1.0",
)

# Một API endpoint "hello world" đơn giản để kiểm tra
@app.get("/")
async def read_root():
    """
    Root endpoint to check if the API is running.
    """
    return {"message": "Welcome to CronPost API!"}

@app.get("/api/health")
async def health_check():
    """
    Health check endpoint.
    """
    return {"status": "ok", "message": "CronPost Backend is healthy!"}

# (Chúng ta sẽ thêm các API endpoint khác cho user, messages, etc. ở đây sau)