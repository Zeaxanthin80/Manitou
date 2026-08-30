# The Next.js storefront and vendor portal, packaged for ECS Express Mode.
#
# **Build from the REPOSITORY ROOT, not from web/:**
#
#     docker build --platform linux/amd64 --provenance=false --sbom=false \
#       --build-arg NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_... \
#       -f web/Dockerfile -t manitou-web:local .
#
# Same constraint as backend/Dockerfile, for a different reason: web/scripts/
# build-tokens.mjs resolves the repo root from its own location and reads
# design-tokens.json and store-config.json from there. Those two files generate
# app/tokens.css, lib/design-tokens.ts and lib/store-config.ts -- all git-ignored,
# so a clone has none of them and the build MUST produce them. `prebuild` in
# package.json runs `npm run tokens` automatically, so `npm run build` is enough.
#
# The root .dockerignore excludes web/ entirely, which is right for the API image
# and fatal for this one. web/Dockerfile.dockerignore overrides it -- BuildKit
# gives <dockerfile-path>.dockerignore precedence, verified on this Docker before
# relying on it.

# node:24 to match the local Node 24, the same reasoning that matched the RDS
# engine to the local Postgres major. Next 16 requires >=20.9.0.
FROM node:24-slim AS deps
WORKDIR /app/web
# npm ci, not npm install: it installs exactly the lockfile and fails if
# package.json and package-lock.json disagree, rather than quietly resolving
# something the developer never tested.
COPY web/package.json web/package-lock.json ./
RUN npm ci

# --- build -------------------------------------------------------------------
FROM node:24-slim AS builder
WORKDIR /app/web
COPY --from=deps /app/web/node_modules ./node_modules

# The two files build-tokens.mjs reads, at the path it expects (repo root).
COPY design-tokens.json store-config.json /app/
COPY web/ ./

# NEXT_PUBLIC_* is inlined into the CLIENT BUNDLE by the compiler, so it has to
# exist at BUILD time -- passing it at runtime would leave the browser with an
# empty string and Stripe Elements would silently fail to mount.
#
# It is therefore baked into the image, and changing it needs a rebuild. That is
# acceptable for this one variable and only this one: the publishable key is
# designed to be public and can only start a payment the secret key already
# authorised. No other secret may be handled this way.
ARG NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=$NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY

# CDN_HOST is also build-time, for a different reason: next.config.ts turns it
# into images.remotePatterns, and Next serialises the resolved config into
# .next/required-server-files.json during the build. Setting it only at runtime
# leaves remotePatterns EMPTY, and next/image then refuses every CDN image --
# which is defect 1's failure mode reached from the opposite direction.
#
# Verified rather than assumed: the first build of this image omitted it, and
#   node -e 'require(".next/required-server-files.json").config.images'
# reported `remotePatterns: []`.
ARG CDN_HOST
ENV CDN_HOST=$CDN_HOST

# API_URL is NOT set here on purpose. It is a plain server-side variable read at
# module scope in lib/api.ts, so the built server reads the real process
# environment at start -- which is what lets one image point at any environment.
# Every route in this app is dynamic, so nothing calls the API during the build.
RUN npm run build

# --- runtime -----------------------------------------------------------------
FROM node:24-slim AS runner
ENV NODE_ENV=production
WORKDIR /app/web

RUN useradd --create-home --uid 10001 appuser

# The two directories `output: standalone` deliberately leaves behind. Next's
# docs expect them to be served by a CDN; they are not yet (task 9), so they are
# copied in. Omit either and the container passes its health check while serving
# an unstyled page with broken images -- which is why verification fetches a CSS
# file and a public/ image rather than trusting the health check alone.
COPY --from=builder --chown=appuser:appuser /app/web/.next/standalone ./
COPY --from=builder --chown=appuser:appuser /app/web/.next/static ./.next/static
COPY --from=builder --chown=appuser:appuser /app/web/public ./public

USER appuser
EXPOSE 3000

# HOSTNAME=0.0.0.0 is not optional. server.js binds loopback by default, and a
# container that binds loopback is unreachable from outside itself -- the same
# mistake as uvicorn's --host, with the same symptom: a process that starts
# cleanly and answers nothing.
ENV PORT=3000 HOSTNAME=0.0.0.0

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD node -e "require('http').get('http://127.0.0.1:3000/api/health',r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"

# Exec form, so node is PID 1 and receives SIGTERM directly rather than through a
# shell that would not forward it.
CMD ["node", "server.js"]
