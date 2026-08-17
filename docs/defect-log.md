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
by hand.

**A rule written more than once.** Defect 4 outright; defect 2 is its cousin, where the message and
the transport were written by different people at different times. Every duplicated rule eventually
disagrees with itself.

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
