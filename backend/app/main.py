from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.middleware import RequestContextMiddleware
from app.routers import address, admin, auth, cart, catalog, order

app = FastAPI(title="Manitou API")

# Makes the client IP available to the audit trail without every audited endpoint
# having to accept a Request. See app/middleware.py.
app.add_middleware(RequestContextMiddleware)

app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(cart.router)
app.include_router(address.router)
app.include_router(order.router)
app.include_router(admin.router)


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
