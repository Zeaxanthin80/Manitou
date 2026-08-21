# Defect Log

Defects found in Manitou, what caused them, and what stops them recurring.

Kept because the same *classes* of mistake keep reappearing in different clothes, and a list of
them is more useful than a list of symptoms. `PROJECT_PLAN.md` says what is still to build; this
says what went wrong and why.

**Conventions.** Newest first. Status is **Fixed** (with the commit) or **Open** (with where it is
tracked). Every entry answers the same four questions: what was seen, what actually caused it, what
was changed, and what makes it not happen again.

---

## Index

| # | Date | Defect | Status |
|---|---|---|---|
| [14](#14-one-payment-per-order-was-enforced-only-by-application-timing) | 2026-08-21 | "One payment per order" was enforced only by application timing | Fixed — uncommitted |
| [13](#13-the-money-conversion-promised-to-refuse-a-fraction-and-rounded-it-instead) | 2026-08-20 | The money conversion promised to refuse a fraction and rounded it instead | Fixed — uncommitted |
| [12](#12-storing-a-config-value-is-not-the-same-as-the-app-reading-it) | 2026-08-19 | Storing a config value is not the same as the app reading it | Fixed `92f6182` |
| [11](#11-cancelling-an-order-never-returns-its-stock) | 2026-08-17 | Cancelling an order never returns its stock | **Open** — Phase 5 task 6 |
| [10](#10-partial-stock-is-invisible-in-the-cart) | 2026-08-17 | Partial stock is invisible in the cart | **Open** — Phase 5 task 6 |
| [9](#9-a-discontinued-product-could-still-be-bought-from-an-old-cart) | 2026-08-17 | A discontinued product could still be bought from an old cart | Fixed `db9dbc0` |
| [8](#8-slug-and-sku-uniqueness-was-case-sensitive) | 2026-08-16 | Slug and SKU uniqueness was case-sensitive | Fixed `6d3f14b` |
| [7](#7-the-product-edit-page-404d-for-any-product-past-the-first-page) | 2026-08-15 | The product edit page 404'd past the first page | Fixed `b083ec4` |
| [6](#6-admin-lists-silently-truncated-at-50-rows) | 2026-08-15 | Admin lists silently truncated at 50 rows | Fixed `5cfdc07` |
| [5](#5-sorting-by-an-aggregate-duplicated-product-rows) | 2026-08-15 | Sorting by an aggregate duplicated product rows | Fixed `5cfdc07` |
| [4](#4-the-reorder-threshold-was-written-out-three-times) | 2026-08-15 | The reorder threshold was written out three times | Fixed `5cfdc07` |
| [3](#3-the-image-picker-offered-files-the-api-would-refuse) | 2026-08-15 | The image picker offered files the API would refuse | Fixed `b76cd7b` |
| [2](#2-validation-messages-never-reached-the-admin) | 2026-08-15 | Validation messages never reached the admin | Fixed `9927535` |
| [1](#1-one-external-image-url-took-down-three-pages) | 2026-08-15 | One external image URL took down three pages | Fixed `9927535` |

---

## 14. "One payment per order" was enforced only by application timing

**Status:** Fixed, uncommitted (migration `4ff248d16b7f`).

**Seen.** Found by reading the `payments` table during the task 2 walkthrough, not by a failure.
`ensure_payment_intent` refuses to open a second payment for an order — but by `SELECT`ing first
and `INSERT`ing after, with nothing between them. `payments.order_id` carried an index and no
unique constraint, so the database had no opinion.

**Cause.** Check-then-act. Two requests arriving together — a double-clicked "Place order", a
retried checkout — both find no row and both insert one.

**Why the damage was bounded.** The Stripe idempotency key is `order-{id}`, so both calls receive
the *same* intent and the duplicate rows share a `stripe_payment_intent_id`. A row that should not
exist, not a second charge. Bounded is not acceptable: a rule the database can state should not be
left to request timing.

**Fixed.** Migration `4ff248d16b7f` drops the non-unique `ix_payments_order_id` and adds
`uq_payments_order_id`. Dropped rather than kept alongside — a unique constraint is a unique index
in Postgres and serves the same lookups, so keeping both would mean two indexes on one column.

**The constraint alone would have made this worse.** It converts a silent duplicate row into an
unhandled `IntegrityError`, which the router turns into a 500 — a customer who did nothing wrong
sees a crash where they previously saw success. So `ensure_payment_intent` now catches it, re-reads
the winning row and retrieves its intent, and returns that. It re-retrieves rather than reusing the
intent it already holds: the idempotency key makes those the same today, and assuming it would hand
back a client secret belonging to a different row if it ever stopped being true. If no winning row
is found the exception is re-raised — that means some *other* constraint fired and there is nothing
to recover.

**Prevented by.** Two tests. One inserts a rival row directly and asserts the database refuses it;
one drives the race with a gateway that commits a competing row on a separate session inside the
window, and asserts one row survives and a usable secret comes back. Mutation-verified both ways:
without the constraint the first reports `DID NOT RAISE` and the second reports `assert 2 == 1`,
which is the duplicate-row defect itself; without the `except IntegrityError`, the race test dies
on an unhandled `UniqueViolation`.

---

## 13. The money conversion promised to refuse a fraction and rounded it instead

**Status:** Fixed, uncommitted (Phase 5 task 2 walkthrough).

**Seen.** Not in production — found by reading `to_minor_units` in `app/services/payments.py`
during the task 2 walkthrough, and confirmed by measuring rather than trusting the comment.

**Cause.** The docstring said `quantize` *"raises if anything is left below the currency's smallest
unit instead of silently dropping it."* `Decimal.quantize` does no such thing by default — it
rounds, half-even, and returns. Measured:

```
JPY 500.50  ->  500     no exception, half a yen dropped
USD 19.999  ->  2000    no exception, rounded UP
```

**Why it mattered more than it looks.** Latent for USD, because `numeric(10,2)` cannot hold a third
decimal, so the input cannot occur. **Live for JPY**, because `numeric(10,2)` stores `500.50`
happily, an admin can type it, and the yen has no minor unit at all. The currencies
`CURRENCY_EXPONENT` exists to protect are precisely the ones a default `quantize()` gets wrong —
the guard was absent exactly where it was needed.

**Fixed.** A `_EXACT` context (`DefaultContext.copy()` with the `Inexact` trap set) and a new
`FractionalMinorUnit(PaymentError)`, so a price the currency cannot express refuses the sale
instead of quietly rounding it. A `PaymentError`, and so a 502, for the same reason
`UnsupportedCurrency` is one: both mean the store is misconfigured, both leave the order saved and
uncharged, both are fixed by an admin.

**The trap inside the fix.** The obvious spelling — `Context(traps=[Inexact])` — is wrong. Passing
`traps=` *replaces* the trap set rather than adding to it, so `InvalidOperation` stops being
trapped and an overflow returns a silent `NaN`. Verified both ways before choosing.

**Prevented by.** Three parametrized cases in `tests/test_payments.py` (JPY 500.50, JPY 500.01,
USD 19.999) plus a subclass check. Mutation-verified: reverting to the plain `quantize` turns all
three red while the nine pre-existing money tests stay green — which is also the proof that the
original suite was blind to this. The pre-existing case `("500.00", "JPY", 500)` *looks* like it
covers zero-decimal currencies and covers only the half that cannot go wrong.

---

## 12. Storing a config value is not the same as the app reading it

**Status:** Fixed in `92f6182`.

**Seen.** Phase 5 task 1 put the Stripe test keys in `backend/.env` — correct keys, correct file,
correctly git-ignored, never committed. The backend then would not start, `alembic upgrade head`
would not run, and `pytest` collected **zero** tests.

**Cause.** `app/config.py` runs `settings = Settings()` at import time, pydantic-settings defaults to
`extra="forbid"`, and `Settings` declared no Stripe fields. So two correctly-stored keys raised
`ValidationError: Extra inputs are not permitted` before a single line of application code ran.

**Why it took down three things at once.** The API, `alembic/env.py` and `tests/conftest.py` all
import `app.config`. A single unreachable module sits underneath the app, the migrations and the
entire test suite, so one config mismatch removed the ability to run the app, change the schema,
*and* detect either problem. The tool that would normally catch a regression was itself a casualty.

**Fixed.** The three fields declared. `stripe_secret_key` as `SecretStr`, because the
`extra_forbidden` error printed the live key into the traceback — harmless on a laptop, but from
Phase 6 that is a boot failure writing `sk_...` into CloudWatch. Adopted while there were zero call
sites; after task 2 it would have been a refactor. `stripe_webhook_secret` is declared now with an
empty default, so task 4 adding it to `.env` cannot reproduce this.

**Prevented by.** `tests/test_config.py` asserts `.env.example` and `Settings` hold the same keys
**in both directions** — a documented key with no field breaks the boot, and a field with no
placeholder leaves a fresh clone unable to start. Verified by mutation: dropping a field reproduces
the original crash, undocumenting one fails cleanly, and adding an undeclared key fails naming it.
That last case is the task 4 rehearsal, since `STRIPE_WEBHOOK_SECRET` lands in `.env` then.

---

## 11. Cancelling an order never returns its stock

**Status:** Open — recorded in `PROJECT_PLAN.md` Phase 5 task 6.

**Seen.** After a probe order was cancelled, the stock count stayed decremented. Putting it back
meant editing the number by hand in `/admin/inventory`.

**Cause.** There is no restock path anywhere in the codebase. `checkout.py` decrements on order
creation and nothing ever adds back. Every cancelled order permanently leaks its inventory.

**Not the same as the reservation work**, which is why it is its own entry: reservations cover
orders that were *never paid*. A paid order has already had stock deducted and takes a different
route back.

**The subtlety worth keeping.** Refunding is not restocking. A cancelled order was never dispatched,
so its stock is still on the shelf. A refunded one may have shipped, and what returns may be
damaged, opened, or never sent back. `→ cancelled` should restock automatically; `→ refunded`
should not, and the vendor restocks deliberately if the goods actually arrive.

---

## 10. Partial stock is invisible in the cart

**Status:** Open — recorded in `PROJECT_PLAN.md` Phase 5 task 6.

**Seen.** A cart line is labelled only when stock hits **zero**. Hold 3 of something, let the vendor
drop to 1, and the cart looks entirely fine until checkout fails with "only 1 in stock".

**Cause.** The cart carries a boolean (`in_stock`), not a count.

**Why it is a decision rather than a fix.** Showing "only 1 left" means publishing an exact figure,
which `VariantRead`'s docstring deliberately avoids for the public catalogue. A count for something
already in that customer's own cart is a much narrower disclosure — but it is still a policy change,
not a silent correction.

---

## 9. A discontinued product could still be bought from an old cart

**Status:** Fixed in `db9dbc0`.

**Seen.** Measured against the test database:

| Step | Result |
|---|---|
| Add to cart while visible | 201 |
| Vendor hides the product | 204 — gone from listing, product page 404 |
| Cart still lists the line | yes, `in_stock` reporting **`true`** |
| Re-adding it | 404, correctly refused |
| **Checkout** | **201. Order placed.** |

**Cause.** `is_active` was checked in exactly one place — the add-to-cart lookup. The cart read did
not filter on it and `checkout.py` never mentioned it. The vendor's "stop selling this" was honoured
everywhere a *new* customer looked and ignored for anyone holding an old cart.

It was invisible beforehand too: `in_stock` is computed purely from `quantity_available`, so a
withdrawn product with stock on the shelf reported `true` and the line looked normal.

**Fixed.** A `ProductUnavailable` guard in `checkout.py`, in the same loop that re-checks stock,
mapped to 409. A separate `is_for_sale` boolean on the cart line, because "out of stock" means
*check back later* and would send a customer away to wait for something never returning.

**Prevented by.** Five tests, including one asserting the exact combination that hid it
(`is_for_sale: false` with `in_stock: true`), and a mutation test: delete the guard and three tests
flip to `assert 201 == 409`.

---

## 8. Slug and SKU uniqueness was case-sensitive

**Status:** Fixed in `6d3f14b`.

**Seen.** A product was created with the slug `Marianao`, giving it the URL `/products/Marianao`
while every other product used lowercase.

**Cause.** Both columns are `UNIQUE`, but Postgres compares text case-sensitively and there was no
`lower()` index, no `citext`, and no normalisation at the API boundary. The database would happily
hold `marianao` **and** `Marianao` as two products with two URLs, or `tee-001` and `TEE-001` as two
SKUs for one shirt. That is not the constraint anyone thought they had written.

**Fixed.** Normalisation in the Pydantic validators — slugs down, SKUs **up**. Opposite directions
on purpose: a slug is a URL, and every SKU in the store is already uppercase, so lowercasing would
have silently rewritten `TEE-CLS-M-BLK` on the next edit. Format is enforced for slugs only; real
SKUs legitimately carry dots and slashes.

**Prevented by.** Tests asserting that creating `marianao` then `Marianao` now returns 409 rather
than quietly producing two products.

---

## 7. The product edit page 404'd for any product past the first page

**Status:** Fixed in `b083ec4`.

**Seen.** Nothing, yet — found by reading. With 7 products it could not bite.

**Cause.** The edit page fetched the whole product list and picked its product out with `.find()`.
The list is paged at 50, so product 51 returned a **404 indistinguishable from a deleted product**.
Adding sorting made it worse: *which* products land in the first page then depends on how the list
was last sorted, so the page could break for a different product each time.

**Fixed.** `GET /admin/products/{id}`. Four lines — `_get_product` and `_to_product` already
existed and eight other endpoints already returned through that exact pair. Only the read route was
missing.

**Prevented by.** A test that pins the property rather than the symptom: with `?limit=1` returning
one row, a product outside that page is still reachable by id.

---

## 6. Admin lists silently truncated at 50 rows

**Status:** Fixed in `5cfdc07`.

**Seen.** Nothing. Found while adding sorting.

**Cause.** `listAdminProducts` defaults to `limit = 50` and neither `/admin/products` nor
`/admin/inventory` rendered `<Pagination>`. Past 50 products, rows vanished with no indication.

**Why it mattered more than it looked.** It ruled out client-side sorting: ordering the rows a page
happens to hold sorts a *slice* of the catalogue while looking authoritative — confidently wrong
the moment there is a second page.

**Fixed.** Pagination on both lists, and sorting moved into the query.

---

## 5. Sorting by an aggregate duplicated product rows

**Status:** Fixed in `5cfdc07` — caught during implementation, never shipped.

**Cause.** Joining `product_variants` to sort by variant count or total stock multiplies the product
rows: a 3-variant shirt comes back three times, and `total` stops matching what is rendered.

**Fixed.** A grouped subquery joined on `product_id`, so the outer query stays one row per product.
`LEFT JOIN`, so a product with no variants still appears rather than vanishing from the list it is
being sorted in.

**Prevented by.** A test asserting a multi-variant product appears exactly once and `total` matches
the row count. Worth having because the failure *looks* like a UI bug and is a SQL one.

---

## 4. The reorder threshold was written out three times

**Status:** Fixed in `5cfdc07`.

**Cause.** `quantity_available <= reorder_level` appeared twice in Python and once in SQL. Adding
sorting by stock status would have made a fourth. Four copies of a threshold is how the storefront
and the portal end up disagreeing about what "low" means.

**Fixed.** A `hybrid_property` on the `Inventory` model. `inv.needs_reorder` in Python and
`Inventory.needs_reorder` in SQL are now the same expression by construction, so the badge and the
sort cannot drift.

---

## 3. The image picker offered files the API would refuse

**Status:** Fixed in `b76cd7b`.

**Seen.** A file named `AI_Celestial Navigation_Orbit-OS.png` appeared as a choice in the picker
and 422'd on submit, with nothing on screen explaining why.

**Cause.** The picker listed every raster file in `web/public/`; the API validator rejects internal
whitespace. **The offer and the guard disagreed** — the same shape as defect 1, one layer up.

**Fixed.** Renamed the file, and `listPublicImages` now filters out names the API would reject, so
an unusable option cannot be offered again.

---

## 2. Validation messages never reached the admin

**Status:** Fixed in `9927535`.

**Seen.** A rejected image URL surfaced in the portal as
`POST /admin/products/36/images -> 422`.

**Cause.** `lib/api.ts` handled a **string** `detail`, which is what `HTTPException` returns.
Pydantic validation errors return an **array** of `{loc, msg, type}`, so the check fell through to
the generic fallback. Every schema-level rejection in the entire app was affected, not just this
one.

**Fixed.** An array branch that joins the `msg` values and strips Pydantic's `"Value error, "`
prefix.

**Worth noting.** A carefully written validator message is worthless if the transport drops it. The
validator and its delivery are one feature.

---

## 1. One external image URL took down three pages

**Status:** Fixed in `9927535`.

**Seen.** A product image was added by pasting a URL from another site. The storefront home page,
the product page, **and the admin product edit page** all threw a runtime error.

**Cause.** `AdminImageCreate.url` was `str = Field(min_length=1)` — any non-empty string. The URL
was stored happily and then failed at **render** time, because `next/image` refuses hosts not listed
in `images.remotePatterns`, and `next.config.ts` deliberately lists none.

**What made it bad rather than annoying.** The admin edit page was one of the casualties, and it is
the only screen that can remove an image. The broken data took down the only tool for fixing it, so
recovery needed `curl`.

**Fixed.** The free-text field became a picker of files actually present in `web/public/` — you
cannot mistype what you cannot type — plus a `field_validator` accepting only site-relative paths.
The validator stays despite the picker, because a Server Action is a directly reachable POST
endpoint and the picker is not its only possible caller.

**Prevented by.** 11 rejection cases, and a mutation test that matters: replacing the guard with the
obvious `startswith("/")` lets **5 of the 11 through**, including `//example.com/shirt.png` — a
browser reads a protocol-relative URL as external, so the naive version looks right and is not.

---

## Recurring shapes

Reading the list back, the same few mistakes keep arriving in different clothes.

**The offer and the guard disagree.** A UI presents something the system then refuses — or accepts
something it cannot render. Defects 1 and 3 are the same mistake at different layers. The fix is
always to derive the offer from the same source as the guard, rather than keeping two lists in step
by hand. Defect 13 is the same disagreement one layer further in, between a
docstring and its own function body: the comment promised an exactness check the code never
performed. A comment is an offer too, and it is the one a future reader will trust instead of
re-deriving the behaviour.

**A rule written more than once.** Defect 4 outright; defect 2 is its cousin, where the message and
the transport were written by different people at different times. Defect 12 is the same shape in
configuration: `.env.example` and the `Settings` class are one list of variables maintained by hand
in two places, and they drifted the first time a variable was added. Every duplicated rule
eventually disagrees with itself.

**Correct today, wrong at scale.** Defects 6 and 7 were both invisible at 7 products and inevitable
at 51. Neither would have been caught by using the app; both were found by reading the code and
asking "what happens when this list is longer than one page?".

**Data outliving the assumption that made it valid.** Defects 9, 10 and 11 are all a cart or an
order holding a fact that was true when it was written and is not true now. Anything durable that
references live state needs re-checking at the moment it is used, not trusted from when it was
created.

---

## Verification failures

Not product defects — mistakes in how the work was *checked*. Kept because a bad check is worse
than no check: it produces confidence without evidence.

- **A verification that could pass without running.** A clone-and-grep check was written as
  `cmd1 && cmd2 && cmd3 || echo "CLEAN"`. The clone failed on authentication and the `||` fired,
  printing a reassuring result that had verified nothing. Now: separate commands, and a control
  case that must fail.
- **A mutation test whose fixtures made it useless.** Inventory rows were created in urgency order,
  so replacing the ordering rule with `ORDER BY id` still passed. Rebuilt with creation order
  deliberately reversed. A mutation test only proves something if the mutant can actually be
  distinguished by the data.
- **Testing against stale code.** An endpoint was probed against a running `uvicorn` started before
  the change and without `--reload`, twice. The result was reported as evidence. Now: check the
  process, or test in-process.
- **Concluding from a 404 without a control.** Probes against GitHub returned 404 and were read as
  "the file is gone". The repository was private, so *everything* returned 404 — including a control
  that should have returned 200. A negative result needs a positive control before it means
  anything.
- **A wildcard that swept up more than intended.** `git add web/public/*.jpeg` committed an image
  that then had to be removed from history and the repository recreated. Add by explicit path, and
  read `git status` before committing.
- **Assuming a string replacement applied.** Twice. A scripted edit to `test_admin.py` left
  `("get", "/admin/products/1", None)` in the route list one commit *before* that endpoint existed
  — the pattern was missing a trailing comma, so it matched nothing and reported nothing. Caught
  only by inspecting the staged file. Then again on `cart/page.tsx`, where the whole "No longer
  available" label silently failed to apply and was discovered at `git add` time, because the file
  was simply absent from the modified list.

  The instructive part: the *same* edit also put a field on the wrong TypeScript type, and `tsc`
  caught that within seconds. The change with a machine checking it was found immediately; the
  change relying on my own assertion was not — because I had not written one. Any scripted edit
  now asserts the text actually changed.
- **Verifying the data instead of the page.** The cart label above was "confirmed" by observing
  `is_for_sale: false` in the API response and concluding the cart was done. The API and the
  rendered page are two different things, and only the easier one was checked — while the label
  did not exist at all. Re-verified afterwards by reading the DOM in both states:
  `["NO LONGER AVAILABLE · REMOVE TO CHECK OUT"]` when hidden, `[]` when visible.

  This is the same shape as *concluding from a 404 without a control*: a result that was true but
  did not mean what it was taken to mean.
- **Treating a value as stored without starting what reads it.** Defect 12. The Stripe keys were put
  in `.env` correctly and the task looked complete — the keys were right, the file was right, and
  nothing was committed that shouldn't have been. Every one of those checks passed while the
  backend could not start at all, because none of them ran the application. "The config is in place"
  and "the app can read the config" are two separate facts, and only the first was established.
  A config task is not finished until something imports it.
- **Mutating a database that the test run rebuilds.** Defect 14. To check that
  `uq_payments_order_id` was really doing the work, the constraint was dropped from `manitou_test`
  with `psql` and the test re-run. It passed — which looked like proof the test was worthless. It
  was not: `conftest.py`'s `engine` fixture runs `DROP DATABASE ... CREATE DATABASE` and
  `alembic upgrade head` at the start of every session, so the constraint was rebuilt before the
  test executed and the mutation never reached the code under test. The mutation has to go in the
  **migration**, since that is what the schema is actually built from. Done properly it failed
  exactly as it should: `DID NOT RAISE IntegrityError`, and `assert 2 == 1` for the duplicate rows.

  Worth noting the direction of this one. The others in this list are false *positives* — a check
  that passed and should not have. This was a false *negative*, a mutation that looked survived and
  was never applied. It would have been reported as "this test proves nothing", removing a guard
  that was working. A mutation test needs its mutation verified as much as its result.
