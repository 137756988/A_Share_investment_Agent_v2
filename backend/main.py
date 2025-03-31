from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import logs, runs

# Create FastAPI app instance
app = FastAPI(
    title="A Share Investment Agent - Backend",
    description="API for monitoring LLM interactions within the agent workflow.",
    version="0.1.0"
)

# Configure CORS (Cross-Origin Resource Sharing)
# Allows requests from any origin in this example.
# Adjust origins as needed for production environments.
origins = ["*"]  # Allow all origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

# Include the logging router
app.include_router(logs.router)
# Include the workflow runs router
app.include_router(runs.router)

# Optional: Add a root endpoint for basic health check/info


@app.get("/")
def read_root():
    return {"message": "Welcome to the A Share Investment Agent Backend API! Visit /docs for details."}
