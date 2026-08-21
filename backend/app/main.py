from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.middleware import RequestContextMiddleware
from app.routers import address, admin, auth, cart, catalog, order
from app.services.payments import validate_gateway_name

# Fail here, at startup, on a payment gateway that does not exist -- rather than
# on the first customer's checkout, which is where a lazily-built dependency
# would have found out. Checks the name only: constructing the gateway would
# import the Stripe SDK and read the secret key, which startup has no reason to
# do. Same instinct as defect 12, this time on purpose.
validate_gateway_name(settings.payment_gateway)

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
