from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.routers import address, auth, cart, catalog, order

app = FastAPI(title="Manitou API")

app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(cart.router)
app.include_router(address.router)
app.include_router(order.router)


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
