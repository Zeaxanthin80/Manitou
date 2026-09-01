from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.middleware import RequestContextMiddleware
from app.routers import address, admin, auth, cart, catalog, order, webhooks
from app.logging_setup import configure_logging
from app.services.payments import validate_gateway_name
from app.store import store_config

# Before anything else that might log. Without this the root logger sits at
# WARNING with no handlers, and every logger.info in the application is discarded
# -- which is what defect 28 was, and why a webhook could answer 200 while
# leaving no record of what it did.
configure_logging()

# Fail here, at startup, on a payment gateway that does not exist -- rather than
# on the first customer's checkout, which is where a lazily-built dependency
# would have found out. Checks the name only: constructing the gateway would
# import the Stripe SDK and read the secret key, which startup has no reason to
# do. Same instinct as defect 12, this time on purpose.
validate_gateway_name(settings.payment_gateway)

# The title is store identity, not a constant: it is public in /openapi.json and
# /docs, so a clone that left it alone would serve another store's name. Reading
# it from store config is the same seam that keeps the store name out of every
# component -- and this was the ONLY place the name had leaked into application
# code. Not a display string the storefront reads; it names the API to whoever
# opens its schema.
#
# The interactive docs are off unless switched on (see Settings.api_docs_enabled).
# Passing None for all three is what actually removes the routes -- hiding the
# links while leaving /openapi.json served would be decoration, since that URL is
# the one worth fetching.
app = FastAPI(
    title=f"{store_config.store.name} API",
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
)

# Makes the client IP available to the audit trail without every audited endpoint
# having to accept a Request. See app/middleware.py.
app.add_middleware(RequestContextMiddleware)

app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(cart.router)
app.include_router(address.router)
app.include_router(order.router)
app.include_router(admin.router)
# No auth dependency by design -- Stripe has no account here, so the request is
# authenticated by its signature instead. See app/routers/webhooks.py.
app.include_router(webhooks.router)


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
