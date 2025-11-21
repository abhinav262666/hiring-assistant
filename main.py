from contextlib import asynccontextmanager

from fastapi import FastAPI

# Import routers from endpoints
from endpoints import router as api_router
from settings import senv


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    print("🚀 Starting Hiring Assistant API...")
    print("✅ Environment variables validated successfully")

    # Setup centralized loggers
    senv.setup_loggers()
    print("📝 Loggers initialized successfully")

    # Initialize database connections
    senv.initialize_databases()
    print("🗄️ Database connections established successfully")

    yield

    # Shutdown logic
    print("🛑 Shutting down Hiring Assistant API...")


app = FastAPI(
    title="Hiring Assistant API",
    description="Backend API for the Hiring Assistant system",
    version="0.1.0",
    lifespan=lifespan,
)

# Include API routers
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "Hiring Assistant API is running", "version": "0.1.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
