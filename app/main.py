from fastapi import FastAPI
from .db import engine, Base # Import engine and Base from your db.py
from .routes import auth, admin, upload, claims, metrics

app = FastAPI(title="Mini RCM Validation Engine")

# Add a startup event handler to create the database tables
@app.on_event("startup")
def create_database_tables():
    # This will create all tables based on the Base and defined models.
    # It will do nothing if the tables already exist.
    Base.metadata.create_all(bind=engine)

# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(upload.router, prefix="/api", tags=["Upload"])
app.include_router(claims.router, prefix="/api", tags=["Claims"])
app.include_router(metrics.router, prefix="/api", tags=["Metrics"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])

@app.get("/")
def root():
    return {"message": "Mini RCM Validation Engine API is running!"}
