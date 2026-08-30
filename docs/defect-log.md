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
| [28](#28-every-loggerinfo-line-is-discarded-in-production) | 2026-08-30 | Every `logger.info` line is discarded in production | Open — Phase 6 task 11 |
| [27](#27-password-reset-links-pointed-at-localhost-in-production) | 2026-08-30 | Password reset links pointed at localhost in production | Fixed — uncommitted |
| [26](#26-the-media-library-shows-uuids-instead-of-filenames) | 2026-08-30 | The media library shows UUIDs instead of filenames | Fixed — uncommitted |
| [25](#25-clicking-blank-space-opened-the-file-manager) | 2026-08-30 | Clicking blank space opened the file manager | Fixed — uncommitted |
| [24](#24-uploaded-images-never-recorded-which-asset-they-came-from) | 2026-08-30 | Uploaded images never recorded which asset they came from | Fixed — uncommitted |
| [23](#23-the-vendor-portal-cannot-bootstrap-a-store) | 2026-08-30 | The vendor portal cannot bootstrap a store | Open — Phase 8 |
| [22](#22-seedpy-could-no-longer-reseed-a-database-that-had-shipped-an-order) | 2026-08-29 | `seed.py` could no longer reseed a database that had shipped an order | Fixed — 86b11a7 |
| [21](#21-any-database-password-containing--broke-alembic) | 2026-08-29 | Any database password containing `%` broke Alembic | Fixed — 86b11a7 |
| [20](#20-a-validation-error-outlived-the-problem-it-described) | 2026-08-22 | A validation error outlived the problem it described | Fixed — a32d114 |
| [19](#19-the-receipt-contradicted-itself-after-payment) | 2026-08-22 | The receipt contradicted itself after payment | Fixed — a32d114 |
| [18](#18-the-cart-emptied-at-the-payment-step) | 2026-08-22 | The cart emptied at the payment step | Fixed — cc1a4c0 |
| [17](#17-an-abandoned-checkout-consumed-its-stock-permanently) | 2026-08-21 | An abandoned checkout consumed its stock permanently | Fixed — 2ba3e4d |
| [16](#16-the-payment-form-rendered-in-a-different-typeface-from-the-rest-of-the-site) | 2026-08-21 | The payment form rendered in a different typeface from the rest of the site | Fixed — 6c80c73 |
| [15](#15-the-payment-page-offered-a-card-form-for-an-order-already-paid) | 2026-08-21 | The payment page offered a card form for an order already paid | Fixed — 6c80c73 |
| [14](#14-one-payment-per-order-was-enforced-only-by-application-timing) | 2026-08-21 | "One payment per order" was enforced only by application timing | Fixed — 989772e |
| [13](#13-the-money-conversion-promised-to-refuse-a-fraction-and-rounded-it-instead) | 2026-08-20 | The money conversion promised to refuse a fraction and rounded it instead | Fixed — 837b4c8 |
| [12](#12-storing-a-config-value-is-not-the-same-as-the-app-reading-it) | 2026-08-19 | Storing a config value is not the same as the app reading it | Fixed `92f6182` |
| [11](#11-cancelling-an-order-never-returns-its-stock) | 2026-08-17 | Cancelling an order never returns its stock | Fixed — 2ba3e4d |
| [10](#10-partial-stock-is-invisible-in-the-cart) | 2026-08-17 | Partial stock is invisible in the cart | Fixed — 2ba3e4d |
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

## 28. Every `logger.info` line is discarded in production

**Status:** Open — fold into Phase 6 task 11 (CloudWatch logs and alarms).

**Seen.** After the first real Stripe webhook delivery returned 200, CloudWatch showed
the uvicorn access line and nothing else. The handler\'s own record of what it did
was absent.

**Cause.** **The application configures logging nowhere.** No `basicConfig`, no
`dictConfig`, no handler. Python\'s root logger therefore sits at its default
`WARNING`, and the "handler of last resort" that writes to stderr is also
`WARNING`. Measured inside the deployed image rather than inferred:

```
logger name     : app.routers.webhooks
effective level : WARNING
handlers        : []          root handlers: []
INFO enabled?   : False       WARNING enabled?: True
```

Which is exactly why the *rejection* warning appeared in CloudWatch during testing
and the *success* line did not.

**Scope today: one line** — `app/routers/webhooks.py`, the only `logger.info` in the
codebase. The two `logger.warning` calls do reach CloudWatch.

**Severity, stated honestly.** That line\'s comment calls it "the record of what
arrived and what was done about it", which overstates it: `apply_payment_event`
writes `audit_events` rows (`payment.confirmed`, `payment.conflict`) in the same
transaction, with `actor` NULL because no human is in the room. **The durable audit
trail is intact.** What is lost is operational visibility — from CloudWatch alone you
can see that a delivery returned 200 but not which order it touched or what outcome
it produced, so "why did this order not flip to paid" is a database question rather
than a log question.

**The dangerous part is the general property, not this one line.** Any `logger.info`
or `logger.debug` added anywhere in this application is invisible in production, and
nothing fails to announce it. The next person to add diagnostic logging will watch it
produce nothing and go looking for a delivery problem.

**Fix (task 11).** Configure logging explicitly at startup — level from an env var
defaulting to INFO, a stdout handler, and leave uvicorn\'s own loggers alone so access
lines are not duplicated. Verify by asserting the effective level inside the built
image, the same way it was measured here, rather than by reading the code.

**The shape to remember, and it is defect 27\'s twin.** Correct code plus absent
configuration, failing silently. Defect 27 was a variable with a working default that
was never set; this is a subsystem with a working default that was never configured.
Both produce a system that starts cleanly, answers 200, and quietly does less than the
code says it does.

---

## 27. Password reset links pointed at localhost in production

**Status:** Fixed (Phase 6 task 10).

**Seen.** Not seen — found by reading the deployed task definition while planning the
domain cutover. `APP_BASE_URL` was absent from the running API\'s environment
entirely, so `config.py` fell back to its default:

```python
app_base_url: str = "http://localhost:3000"
```

That string builds the reset link in `app/routers/auth.py:369` and
`app/routers/admin.py:1799`. Every password-reset email generated in production
carried `http://localhost:3000/reset-password?token=…`.

**Cause.** A default that is correct in development and wrong everywhere else,
combined with a variable nobody had to set for the app to start. Nothing failed:
the API booted, the endpoint answered 200, the token was minted and stored
correctly, and the audit row was written. Only the link was useless.

**Why nothing caught it.** Tests set `APP_BASE_URL`, so they assert the link is
built from it — correctly, and without ever asking whether production sets it.
The deployment had no equivalent check because it is configuration, not code. And
`EMAIL_SENDER=console` meant the wrong link was printed to CloudWatch rather than
delivered, so there was no bounced mail, no user complaint, and no error anywhere.
**The bug was scheduled to become visible at the moment real email was switched
on** — the worst possible time to discover it.

**Fixed.** `APP_BASE_URL=https://imprimapress.com` added to the API service, and
`.env.example` now says the variable must be set in every deployed environment and
why the default is dangerous.

**The shape to remember: a working default is not a set value.** Required
configuration should be *absent* by default and fail loudly at startup, the way
`DATABASE_URL` does — `config.py` refuses to boot without DB_HOST/DB_USER/DB_NAME/
DB_PASSWORD, which is why that class of mistake cannot happen there. Anything with
a localhost fallback will eventually ship to production still holding it. Worth
auditing the rest of `Settings` for the same pattern.

---

## 26. The media library shows UUIDs instead of filenames

**Status:** Fixed, uncommitted (Phase 6 task 9b).

**Seen.** Every asset in the deployed media library was labelled with a hex string —
`70eabec67c3c4d70b76dcf8…` — rather than the name of the file the vendor uploaded.
Noticed by the owner on the first real use of the library.

**Cause.** The filename is collected at the step that cannot store it, and absent
from the step that can.

`POST /admin/uploads` (presign) accepts `filename`, validates it at 1–255
characters, and **never reads it** — correctly, because presigning writes no row.
`POST /admin/uploads/confirm` writes the row and has no filename field at all, so
it reconstructed one:

```python
original = payload.key.rsplit("/", 1)[-1]
```

The key is `media/YYYY/MM/{uuid4().hex}.jpg`, so that is the generated UUID. The
docstring three lines above it says the original filename "is kept for the media
library\'s search"; the code stored something that has nothing to do with the
vendor\'s file.

**Why the test did not catch it — the test encoded the bug.** One test asserts the
stored filename, and it posts a hand-written key:

```python
key = "pending/2026/08/abc.jpg"
assert row.original_filename == "abc.jpg"   # comment: "never part of the key"
```

Its basename was chosen to *look* like a filename, so the key-derived value and the
real filename are the same string and the assertion cannot tell them apart. The
comment on that line states the invariant the code violates, directly above an
assertion that cannot detect the violation. **Fixture data that resembles the right
answer will confirm the wrong implementation.**

**Fixed.** `original_filename` moved onto `AdminUploadConfirm`, sent by the browser
at confirm time — it still holds the `File`, so nothing needs to be carried across
the round trip. The endpoint sanitises it for storage (basename only, printable
characters, length-capped) and it remains barred from key construction, which is
what the presign comment was always about. The test now posts a UUID-shaped key and
a different filename, so the two are distinguishable and the assertion means
something.

**The shape to remember.** Same as defect 24: a value that crosses two endpoints,
each individually correct, lost in the gap between them. Defect 24 was a column
never written; this is a column written with the wrong source. **When a field exists
to answer a question, test it with data that could only have come from the intended
source** — here, a filename that appears nowhere in the key.

---

## 25. Clicking blank space opened the file manager

**Status:** Fixed, uncommitted (Phase 6 task 9b).

**Seen.** On the deployed vendor portal, the upload control's click target extended
far past the visible **Choose File** button — clicking apparently empty space to its
right opened the OS file picker. Found by the owner clicking around production, and
identified in DevTools as the `input[type=file]`, reported at `clientWidth: 672`.

**Cause.** A Tailwind default, two elements up:

```
<form className="… max-w-2xl">          672px  (42rem at a 16px root)
  <fieldset className="flex flex-col">  align-items: stretch — the default
    <input type="file" />               stretched to 672px
```

A flex column stretches its children to the full cross-axis width unless told
otherwise. The `file:` variant styles only the **button pseudo-element** *inside*
the input; the remaining ~570px of stretched box is still the input, and every
pixel of an `input[type=file]` activates the picker. So the styled affordance and
the hit area were different rectangles, and only one of them was visible.

**Why nothing caught it.** Nothing could. `tsc`, ESLint and the production build all
pass on it — it is valid markup, valid CSS and correct Tailwind. It is not an
accessibility fault either: the element reported the right accessible name, a
`button` role and keyboard focusability, so an audit would call it clean. A pointer
landing somewhere that looks empty is visible only to a person using a mouse on a
real page, which is exactly how it was found.

**Fixed.** `w-fit` on the input, so it shrinks to its intrinsic width and the
control and the click target become the same rectangle. Verified the number rather
than the appearance: `--container-2xl` resolves to `42rem` in the built CSS, and
42 × 16 = 672 — the same figure DevTools reported, which is what made the cause
proven rather than plausible.

**The lesson is about pseudo-elements, not about this input.** `file:`, `before:`,
`after:` and `placeholder:` all style something *within* an element's box. Styling
one says nothing about the box's size, so a small, pretty pseudo-element inside a
stretched parent silently grows the interactive region. The second time a Tailwind
layout default has produced a surprising box in this phase — the first was
`remotePatterns` reading empty because `CDN_HOST` was absent at build time — and
both were found by measuring the artefact rather than reading the source.

---

## 24. Uploaded images never recorded which asset they came from

**Status:** Fixed, uncommitted (Phase 6 task 9b).

**Seen.** After the first real upload reached production, `product_images` and
`media_assets` held two rows that should have been one:

```
 id | asset_id | asset_row | url
----+----------+-----------+-------------------------------------
  1 |          |           | https://d2xp3jc….cloudfront.net/media/…
    |          |         1 |
```

A `FULL OUTER JOIN` on the foreign key matched nothing.

**Cause.** Task 9's migration added `product_images.asset_id` and the FK; the
write path never set it. `confirm_upload_target` returned the asset, the web
action kept only its `url`, and `add_product_image` had no field for the id. Each
piece looked complete on its own.

**Why the tests did not catch it.** Every test wrote `ProductImage` rows for its
own purposes and none of them cared where the image came from -- and the upload
tests stopped at the asset row, because that is what the upload endpoint returns.
The gap lived exactly between two well-tested things, which is where this kind of
gap always lives.

**Why it mattered more than a null column.** `media_assets` exists to answer one
question S3 cannot: *which products use this?* With the column empty the answer
was always "none". The `NO ACTION` FK -- the guard meant to stop an asset being
deleted while a product still shows it -- protected nothing, because nothing
referenced anything. Task 9b's delete would have reported every asset as unused
and removed one a live product was displaying.

**Fixed.** `AdminImageCreate` gained `asset_id`, the web action threads it from
`confirmUploadAction` through a hidden field, and `AdminImageRead` exposes it.

**The part worth keeping is the check, not the column.** The endpoint loads the
asset and verifies the submitted url resolves to that asset's key -- 404 for an
id that does not exist, 409 for one that does not match. Populating the column on
trust would have been worse than leaving it null: a mismatched id is a confident
WRONG answer where a null is an honest absent one, and a delete guard reading it
would refuse the wrong assets and permit the rest.

Mutation-tested three ways -- storing `None`, dropping the match check, dropping
the existence check -- each fails a different test.

**What makes it not happen again.** A column added by a migration is not evidence
that anything writes to it. The check that would have caught this is the one this
task ran before starting: `SELECT` the new column against real data and see
whether it is populated. Task 9 verified the upload, the object, the CDN and the
render -- every link except the one joining the two tables it had just created.

---

## 23. The vendor portal cannot bootstrap a store

**Status:** Open. Worked around in production by inserting categories with SQL;
tracked for Phase 8. Owner-reported, on the first attempt to use the live store.

**Seen.** A fresh production database, an admin signed in, and no way to create a
product. `/admin/products/new` requires a Category, the dropdown is empty, and
nothing anywhere in the portal creates one.

**Cause.** Categories are readable and nothing else:

- the API exposes `GET /categories` and `GET /categories/{slug}` — no POST, PATCH
  or DELETE, in the public router or the admin one
- there is no `/admin/categories` page
- `products.category_id` is NOT NULL, so no product can exist without one
- categories have only ever existed because `seed.py` creates them — and
  `seed.py` refuses to run against anything non-local (defect 22), correctly

So on an empty database every route to a first product is closed, and the only
way out is a database client. PROJECT_PLAN Phase 4 specced products, inventory,
orders and a summary view; category management was never on the list, because
every environment that had ever been developed against was already seeded.

**Why five phases missed it.** The gap is invisible wherever `seed.py` has run,
which is every local database and every test database. It can only appear on a
schema built by migrations alone — which happened for the first time in Phase 6
task 5, and was only *noticed* in task 9, when someone tried to add a product to
it. A test suite that builds its own data cannot find this: the missing thing is
not a behaviour, it is a screen.

**Not fixed now, deliberately.** It surfaced mid-way through verifying an image
upload, and category CRUD is a feature rather than a patch: endpoints, schemas,
an admin page, and a delete rule. `products.category_id` is `NO ACTION`
(confirmed in `pg_constraint`), so the database already refuses to delete a
category that has products — the endpoint should turn that into a message naming
them rather than an IntegrityError, the same treatment `media_assets` will need
in task 9b.

Fixing it hastily while the store is live is how a second defect gets written.

**Worked around** by inserting the tree `seed.py` builds — Apparel with T-Shirts
and Accessories underneath — directly into RDS. That keeps local and production
agreeing, and is reversible only with more SQL, which is itself the argument for
building the screen.

**What makes it not happen again.** The class of question, rather than this
instance: *can a brand-new install of this store be set up entirely through its
own interface?* Every clone of this repo starts with an empty database, and the
Section 1.1 reusability seams promise a store can be adapted by editing config
and content. A setup step that requires `psql` breaks that promise. Phase 8 is
launch readiness, and this is exactly a launch-readiness question.

---

## 22. `seed.py` could no longer reseed a database that had shipped an order

**Status:** Fixed in `86b11a7` (Phase 6 task 5).

**Seen.** `python seed.py` against the local development database died with
`ForeignKeyViolation: update or delete on table "orders" violates constraint
"fk_shipments_order_id_orders" — Key (id)=(108) is still referenced from table "shipments"`.

**Cause.** `DELETE_ORDER`, a hand-written tuple naming every model in dependency order, was written
in Phase 1 and never updated. Phase 5.5 added `shipments` and `shipment_events`; neither was in the
list, so `DELETE FROM orders` ran while a shipment still pointed at one. It only surfaced after an
order had actually been dispatched locally, which is why five phases passed without noticing.

**The obvious fix would also have failed.** Adding the two models to the list moves the failure
rather than removing it: `shipment_events` and `audit_events` carry a trigger that rejects `DELETE`
outright. A delete-based wipe cannot clear an append-only table at all.

**Fixed.** `wipe(session)` replaces the loop, using exactly what `tests/conftest.py` already does —
`TRUNCATE … RESTART IDENTITY CASCADE` over table names read from `pg_tables`, excluding
`alembic_version`. Two properties matter and neither is incidental:

- **Read from the catalogue, so it cannot go stale.** The bug was a second hand-maintained list of
  every table. A migration that adds one is now picked up with no edit here.
- **TRUNCATE does not fire row-level triggers,** so it passes the append-only guards where `DELETE`
  cannot. `CASCADE` also removes the need to encode a dependency order by hand at all.

The tuple survives, renamed `REPORTED_MODELS`, for the summary printed at the end — which is what it
is actually used for now.

**Verified against the data that broke it**, not a clean database: 45 orders, 2 shipments, 8
shipment events and 136 audit events. All cleared, ids restarted, and the append-only trigger still
rejects an `UPDATE` afterwards — TRUNCATE empties a table without disarming it.

---

## 21. Any database password containing `%` broke Alembic

**Status:** Fixed in `86b11a7` (Phase 6 task 5).

**Seen.** The first `alembic upgrade head` against RDS raised
`ValueError: invalid interpolation syntax in 'postgresql://…' at position 32` — before any
connection was attempted, and with the entire connection string quoted back in the message.

**Cause.** `alembic/env.py` passes the URL to `config.set_main_option`, which writes through
`configparser`, where `%` begins an interpolation token. RDS had generated a master password
containing `#`; percent-encoding it for URL-safety produced `%23`, and configparser rejected it.

Two encodings with incompatible rules for the same character, one wrapped inside the other. Local
development never hit it because `devpassword` has no special characters — the code was wrong for
five phases and nothing could reveal it until a password was generated rather than chosen.

**Fixed.** `settings.database_url.replace("%", "%%")` at the one call site, `%%` being configparser's
own escape. Verified as a round trip in both directions: four URLs — plain, `%23`, `%29 %23`, and a
literal `%%` — all come back identical through `set_main_option`/`get_main_option`, and the two
encoded cases still raise without the escape, which is what makes the escape load-bearing rather
than decorative.

**Worth its own note: the error message published the password.** Anything that quotes a connection
string back is a credential disclosure, and here it went to a terminal and then into a screenshot.
Had it surfaced one task later, the same traceback would have gone to CloudWatch Logs with 90-day
retention. The RDS master password was rotated.

---

## 20. A validation error outlived the problem it described

**Status:** Fixed in `a32d114`. Owner-reported.

**Seen.** "Your card number is incomplete." sitting under a fully entered card — 4242 4242 4242 4242,
expiry, CVC and ZIP all present — with the Pay button still offering to charge.

**Cause.** The message is OURS, not Stripe's. It is set from `stripeError.message` when a submit
fails and nothing ever took it down. Stripe's Element does per-field validation inside its iframe
and updates as you type; our form-level error had no such lifecycle.

**Fixed.** `<PaymentElement onChange={() => setError(null)}>`. The message clears the moment the
customer touches the form — the same gesture that begins fixing it.

**The button stays ENABLED, deliberately.** Disabling submit until a form validates is a familiar
pattern and a poor one: it removes the feedback loop, so a customer who cannot proceed has no way to
ask why. An enabled button that explains what is missing, and an error that disappears when they
start correcting it, beats a dead button every time.

---

## 19. The receipt contradicted itself after payment

**Status:** Fixed in `a32d114`. Owner-reported.

**Seen.** A paid order rendering "THANK YOU" above "Your order is saved and nothing has been
charged. Complete payment.", with a cart badge counting goods that were already gone. On another
screen the cart page said "Your cart is empty" beside a badge reading 2.

**Two separate causes with one symptom**, which is why it took two wrong diagnoses to find:

**(a) A page rendered while its data was still momentarily wrong, then cached.** Payment is
confirmed by Stripe talking to the WEBHOOK, server to server. The browser never hears about it. The
old flow called `router.refresh()` then `router.push()` — refreshing the page being LEFT, and
rendering the receipt at the one instant the order was still `pending` and the cart still full.
Next.js then served that cached payload back. The header badge lives in the root layout and is
cached separately from the page body, which is how the two came to disagree.

**(b) The heading said "Thank you" unconditionally.** Wrong on a *fresh* render too, and newly
reachable for good: defect 18 made carts survive abandonment, so a customer can now sit in the
unpaid state indefinitely and return to a page thanking them for something they never bought.

**Fixed.** A Server Action, `paymentSettledAction`, runs before navigating: it re-retrieves the
intent from Stripe so `payments.status` is current without waiting for the webhook, then calls
`revalidatePath('/', 'layout')`, which is what discards the cached payloads — including the layout
the badge lives in. And `orderHeading()` derives the heading from the same two signals the body
uses, so the six status/payment pairings can no longer contradict each other.

**What it deliberately does NOT do.** It does not mark the order paid from the browser's word.
Between Stripe accepting the card and the webhook landing, the receipt says "Payment received — we
are confirming your order now", which is true. Making it say "Paid" instantly would mean trusting
the one party with a reason to lie about money.

**The shape worth keeping.** Every other entry in this log is about verifying the wrong thing. This
one is about a render being *true when it happened* and false a second later — correctness with a
timestamp. Anything that caches a view of state changed by an out-of-band event has it.

---

## 18. The cart emptied at the payment step

**Status:** Fixed in `cc1a4c0`. Owner-reported.

**Seen.** Clicking "Continue to payment" emptied the cart and zeroed the badge — before any money
moved. Abandoning at the card form left the customer with nothing.

**Cause.** `create_order_from_cart` deleted the cart lines at order creation.

**Why it was wrong.** The owner's analogy: the clerk scans your goods out of the trolley, but if you
say "hold on, do not ring that up", you do not walk away empty-handed. Every major platform keeps
the cart until payment SUCCEEDS — abandonment runs around 70%, and a cart that still holds its items
is the entire basis of cart recovery. Emptying at the payment step throws that away and punishes a
customer who merely wanted to add one more thing.

Same root as defect 17, one layer up: both treated "started to check out" as "bought". Task 6 fixed
it for stock; this fixed it for the cart. The test guarding it has now been renamed twice for
exactly that reason.

**Fixed.** The cart survives; `apply_payment_event` consumes it when money actually arrives, and
subtracts the ordered quantities rather than emptying — so a jumper added after checking out is not
silently binned. Checking out again supersedes any existing unpaid order, so one customer cannot
hold the same units under two pending orders (task 6 derives reservations from pending order items).

**Safe against the tab-left-open case** by machinery that already existed: if a superseded order's
payment lands anyway, `apply_payment_event` refuses to revive a cancelled order and writes
`payment.conflict` instead (defect from task 4's design, not a new guard).

---

## 17. An abandoned checkout consumed its stock permanently

**Status:** Fixed in `2ba3e4d` (Phase 5 task 6).

**Seen.** Eight orders sitting `pending` in the development database, none of them paid, every one
still holding stock it had taken at placement. A product could read sold out having earned nothing,
and nothing on any screen explained why.

**Cause.** `checkout.py` did `quantity_available -= line.quantity` at order creation — before any
money moved.

**This code was CORRECT when it was written**, which is the part worth keeping. While `pending →
paid` was a human decision, an order was as good as a sale and deducting immediately was right. It
became wrong the moment Phase 5 made payment a separate step that can simply never happen. Nothing
edited it into being a bug; the world around it changed.

The same shape as *data outliving the assumption that made it valid*, one level up: it was the CODE
outliving its assumption. Worth watching for whenever a manual step becomes an automated one — the
question is not "is this still correct?" but "what was this relying on that is no longer true?"

**Fixed.** `quantity_available` now means one thing only: what is physically on the shelf. What
pending orders hold is DERIVED, never stored (`app/services/stock.py`), and the pending order *is*
the reservation — its `order_items` rows are the hold. Placing an order writes nothing extra,
releasing one is just the status changing, and a missed release cannot happen because there is no
counter to drift. Expiry is one `WHERE` clause instead of a scheduled sweep.

**The dangerous part was the five call sites.** "Is there stock?" is asked by the oversell guard,
the storefront, the cart, add-to-cart and the admin inventory view. A site left comparing against
`quantity_available` would not merely weaken the guard — it would REMOVE it, because that column no
longer moves at placement. Measured: reverting the checkout guard alone let 8 concurrent buyers sell
the same 3 units.

**Prevented by.** 23 tests in `tests/test_stock.py`. Each of the five sites is pinned by its own
test, verified by reverting each one individually and confirming exactly one test fails. The
concurrency guard is mutation-tested both ways — removing the row lock, and reading the shelf count
instead of sellable, each produce `sold 8, only 3 existed`.

**Measured rather than assumed.** Deriving costs an aggregate per read, so it was benchmarked on
1,500 variants and 40,000 order lines before deciding: customer-facing paths are ~1 ms, because the
catalogue listing never asks. The numbers are in `stock.py`'s docstring.

---

## 16. The payment form rendered in a different typeface from the rest of the site

**Status:** Fixed in `6c80c73` (Phase 5 task 3). Owner spotted it; four attempts to fix it.

**Seen.** The Stripe Payment Element rendered in the system font while every other page used Inter.
`appearance.variables.fontFamily` was already set to `"Inter, system-ui, sans-serif"` and was doing
nothing.

**Cause.** `next/font` self-hosts Inter under a *generated* family name and declares its
`@font-face` in our document. The Elements iframe is a different document, served by js.stripe.com,
and cannot see that declaration. No font called "Inter" existed inside it, so it fell through to
`system-ui`.

**The same shape build-tokens.mjs already documents** for `@theme` vs `@theme inline`: a font name
that resolves in one scope and not another, failing by quietly rendering a fallback rather than by
erroring. That comment was read during this task and the trap walked into anyway.

**Fixed** by passing `fonts: [{ cssSrc: "https://fonts.googleapis.com/css2?family=Inter..." }]` to
`<Elements>`.

**Self-hosting was tried first, twice, and measured to fail.** A `CustomFontSource` pointing at
`/public/fonts/inter-latin.woff2`, then a `cssSrc` pointing at our own stylesheet with a matching
CORS header. In both cases the browser fetched the stylesheet and **never requested the font** --
not a 404, not a CORS rejection, no request at all.

**That signature is the reusable lesson.** A font that fails with *zero* network activity has been
refused before the request: mixed content, or a Content-Security-Policy font-src. A font that fails
*with* a request is a 404, a CORS problem or a bad path. The two have completely different causes
and the Network panel distinguishes them in one glance.

**The cause here is still not settled, and Phase 6 must retest.** Two explanations fit equally:
Stripe's iframe allowlisting font sources, or plain mixed content -- dev serves `http://localhost:3000`
while the iframe is https, and browsers block http subresources in an https document silently. If it
is the second, self-hosting will work once Phase 6 serves HTTPS and this should go back to our own
origin, restoring layout.tsx's "the browser makes no request to Google". Untestable until an HTTPS
origin exists.

**Also learned: Stripe validates appearance rules and says so in the console.**
`[Stripe.js] stripe.elements(): "fontFamily" is not a supported property for ".Block"` was printed
for two rounds before anyone read it. Not the cause of this defect, but it was free information
sitting in a panel nobody opened.

---

## 15. The payment page offered a card form for an order already paid

**Status:** Fixed in `6c80c73` (Phase 5 task 3).

**Seen.** The owner pressed "Pay", then reloaded shortly after. Navigating back to
`/orders/{id}/pay` for an order whose payment had already succeeded rendered a live card form for
something already bought. Orders 77, 78 and 80 were all sitting in that state.

**Cause.** `/orders/[id]/pay` guarded on `409 OrderNotPayable`, which the API raises when
`orders.status != "pending"`. But **only the task 4 webhook writes `orders.status`, and task 4 does
not exist** — so for the entire duration of task 3 an order can be paid at Stripe and `pending`
here simultaneously. The guard could not fire. Measured:

```
order.status         : pending
POST payment-intent  : 201
returned status      : succeeded
hands back a secret? : True
```

**Not an API bug.** Create-or-retrieve has to keep working, and the task 4 webhook will retrieve
exactly this state. The endpoint reporting `succeeded` is correct; the page ignoring the status it
was handed is not.

**Fixed.** The page redirects to the receipt when `intent.status` is `succeeded` or `processing`.
Deliberately **not** `requires_action` — that is a 3-D Secure challenge in progress, and the form is
where it must resume.

**Why it was low-harm and still worth fixing.** Stripe refuses to confirm one intent twice, so no
double charge was possible. The cost was a customer staring at a form that cannot work, right after
handing over a card — the exact moment to avoid making someone doubt whether their money moved.

**Prevented by.** `test_a_succeeded_payment_still_returns_a_secret_not_a_409` pins the API contract
the page now branches on, so anyone who later makes that endpoint refuse instead learns a page
depends on the current answer. Verified live in both directions: order 77 (paid) redirects, order 79
(unpaid) still renders the form — the second being the control that proves the redirect is
conditional rather than unconditional.

---

## 14. "One payment per order" was enforced only by application timing

**Status:** Fixed in `989772e` (migration `4ff248d16b7f`).

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

**Status:** Fixed in `837b4c8` (Phase 5 task 2 walkthrough).

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

**Status:** Fixed in `2ba3e4d` (Phase 5 task 6). Open for four days.

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

**Fixed.** `restock_for_order` in `app/services/stock.py`, called from the admin status transition
**in the same transaction as the status change** — split across two commits you could end up with an
order marked cancelled and stock still missing, which nothing afterwards could distinguish from an
order that legitimately shipped.

The condition is `previous == "paid" and payload.status == "cancelled"`, and **both halves are
load-bearing**:

- Drop `previous == "paid"` and cancelling a *pending* order manufactures stock out of an abandoned
  checkout — the mirror image of this defect, and just as wrong.
- Widen it to include `refunded` and the store invents inventory that may be shipped, damaged, or
  never coming back.

Every restock writes an `inventory.restocked` audit row naming the lines and the reason, because
"where did those twelve units come from?" has to be answerable.

**Prevented by.** Four tests in `tests/test_stock.py`, mutation-verified individually: removing the
restock, widening it to refunds, and dropping the `previous == "paid"` guard each fail exactly one
test. Confirmed end to end against the running app — a paid order for 2 units cancelled, and the
shelf went 0 → 2 with the audit row to match.

---

## 10. Partial stock is invisible in the cart

**Status:** Fixed in `2ba3e4d` (Phase 5 task 6). Open for four days.

**Seen.** A cart line is labelled only when stock hits **zero**. Hold 3 of something, let the vendor
drop to 1, and the cart looks entirely fine until checkout fails with "only 1 in stock".

**Cause.** The cart carries a boolean (`in_stock`), not a count.

**Why it is a decision rather than a fix.** Showing "only 1 left" means publishing an exact figure,
which `VariantRead`'s docstring deliberately avoids for the public catalogue. A count for something
already in that customer's own cart is a much narrower disclosure — but it is still a policy change,
not a silent correction.

**Decided: publish the count.** `CartLineVariant` gained `quantity_sellable`, deliberately NOT
`VariantRead` — the public catalogue keeps its no-exact-counts posture, and this is a number about a
line the customer already holds.

**Fixed.** The cart line now has three states rather than two, in strict precedence:

| condition | label |
|---|---|
| product withdrawn | No longer available · remove to check out |
| sellable is 0 | Out of stock |
| sellable < line quantity | **Only N left · reduce to check out** |

Discontinued wins over both, and the order of the branches is what enforces it: "Out of stock" means
*check back later*, which is exactly the wrong advice for something that is never coming back.

**Verified on the rendered page, not the API response.** The web app has no test tooling at all — no
vitest, no testing-library, no test files — so the page was driven through Next.js and the labels
read out of the DOM at each state: stock 19 → no label, stock 1 → "Only 1 left", stock 0 → "Out of
stock", stock 1 + withdrawn → "No longer available". That last row is the precedence claim.

Done that way deliberately: *verifying the data instead of the page* is already an entry in the
verification failures below, from the discontinued-cart work on this same component.

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

**CODE outliving the assumption that made it correct.** Defect 17 is the same shape one level up.
`quantity_available -= qty` at order placement was right while `pending → paid` was a human
decision, and became wrong the moment payment turned into a step that can never happen. Nobody
edited it into being a bug. The useful question when automating something a person used to do by
hand is not "is this still correct?" but "what was this relying on that is no longer true?" 

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
- **Writing a guard without watching it fire.** Defect 15. `/orders/[id]/pay` was given a `409`
  branch for "this order cannot be paid", and it was never exercised — because the condition it
  tested (`orders.status != "pending"`) cannot occur while task 4 is unbuilt. The code read as
  though the case were handled. The suite passed. The branch was dead on arrival. *A guard you have
  never watched fail is not a guard* was already the rule here for mutation testing; it applies just
  as hard to a branch that no test and no manual step ever reached.
- **A verification instruction vague enough to be read two ways.** The step written for the owner
  was "reload `/orders/{id}/pay` mid-payment". That covers two different tests — reloading *before*
  touching the form (which only exercises create-or-retrieve, and was already working) and paying
  *then* returning (which is what found defect 15). The owner picked the second and had to ask what
  had been meant. A verification step should name the actual actions — which button, in which order,
  and what to look for — not a state of affairs the reader has to interpret. The useful test was
  found despite the instruction, not because of it.
- **Not reading the console while chasing a rendering bug.** Defect 16. Three rounds of network
  captures, doc fetches and headless probes went by with
  `[Stripe.js] "fontFamily" is not a supported property for ".Block"` printed in the browser console
  the whole time — visible in two screenshots before anyone looked at it. It was not the cause, but
  it was free evidence that Stripe validates the appearance object and reports what it rejects,
  which would have narrowed the search immediately. When a third-party widget renders wrongly, its
  own console output is the cheapest thing to check, and it was checked last.
- **Testing in an environment that cannot reproduce the target.** Defect 16 again. Two headless
  Chrome probes were built to prove whether the font loaded; in both, the Payment Element never got
  past its skeleton state, so no text was ever rendered, so no font was ever requested — a result
  indistinguishable from the bug itself. Conclusions were nearly drawn from it anyway. A probe that
  cannot reach the state under test produces the same output as a failure and is worth nothing.
- **A silent success taken as evidence.** Cancelling order 75 was run with
  `docker exec` and no `-i`, so the heredoc was discarded, psql read nothing and exited 0. No output,
  no error, no transaction. It surfaced only because the verification query was a separate command
  that looked at the actual rows. Exit status and empty output are not evidence that an action
  happened — the same shape as the `|| echo "CLEAN"` entry above.
- **Comparing two things that are both zero.** Task 6. The derived reservation was checked against an
  independently hand-computed sum across the whole development database: zero mismatches, which
  looked like proof. It was not — every pending order was hours past the 30-minute window, so both
  sides were summing an empty set and agreeing that nothing is nothing. Widening the window until
  six variants actually reserved is what turned it into evidence. A comparison only tests what it
  can distinguish.
- **A mutation applied to the wrong function.** Task 6, and the second time in two days. A guard was
  mutated with `s.replace(old, new, 1)` where `old` — `if order.status != "pending":` — appears twice
  in the file, so the FIRST occurrence was hit and the code under test was never touched. The test
  passed and read as "this guard is untested". Retargeting by line number failed it correctly. The
  entry about this already existed in this list and did not prevent the repeat: a written lesson is
  not a habit, and the durable fix is to assert the match is unique before replacing, which the later
  edits in this task did.
- **Reading a response body before checking its status.** Task 6. Five tests failed with
  `KeyError: 'items'`, which reads like a bug in the endpoint. It was `?limit=200` exceeding
  `MAX_PAGE_SIZE = 100`, so the API answered 422 and the test was pulling `items` off an error body.
  The error named the test's own shape and sent the search to the wrong place. Assert the status
  first; a 4xx should say so, not surface three lines later as a missing key.
- **Diagnosing a mechanism from a screenshot.** Defect 19, twice in a row. The first reading was "a
  race between the redirect and the webhook"; the second, looking at a page whose body said "Your
  cart is empty" beside a badge reading 2, was "the badge is stale". The database said the badge was
  right and the BODY was stale — the exact opposite. Both readings were built from a picture plus a
  plausible story, and a picture cannot show which of two disagreeing numbers is the wrong one.

  What settled it took ten minutes: register a probe account, drive the whole flow with curl, and
  ask the Next.js server what it renders with no browser involved. Server correct at every layer,
  staleness entirely client-side. A screenshot is evidence that something is wrong, never evidence
  of why.
- **Verifying the layer that was never broken.** Defect 19 again. Those curl checks proved the
  server renders correctly at every payment state — which was equally true BEFORE the fix, because
  the bug was never server-side. Confirming it after the change felt like verification and
  established nothing about whether the fix worked. Only a real browser doing a real payment could,
  and the owner did that. When a bug is in a cache, testing the thing being cached tests the wrong
  end.

