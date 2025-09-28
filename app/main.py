from fastapi import FastAPI
from .db import init_db
from .routes import auth, admin, upload, claims, metrics

app = FastAPI(title="Mini RCM Validation Engine")

init_db()

# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(upload.router, prefix="/api", tags=["Upload"])
app.include_router(claims.router, prefix="/api", tags=["Claims"])
app.include_router(metrics.router, prefix="/api", tags=["Metrics"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])

@app.get("/")
def root():
    return {"message": "Mini RCM Validation Engine API is running!"}
