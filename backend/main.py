from fastapi import FastAPI

#Initialise the FastAPI app
app = FastAPI(
    title = "NetGen Pro API",
    description = "Backend engine for Network Management System",
    version = "1.0.0"
)

#Create our very first API Endpoint (a simple health check)
@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "NetGen Pro Backend is locked and loaded!",
        "engine": "FastAPI"
    }