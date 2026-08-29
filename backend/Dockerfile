# The API, packaged for ECS Express Mode.
#
# **Build from the REPOSITORY ROOT, not from backend/:**
#
#     docker build --platform linux/amd64 -f backend/Dockerfile -t manitou-api:local .
#
# The context has to be the root because app/store.py reads store-config.json at
# import time from `Path(__file__).resolve().parents[2]` -- one level ABOVE
# backend/. Copying backend/ alone into /app would make parents[2] resolve to `/`
# and the container would die on import, before FastAPI starts, complaining about
# a path nobody wrote.
#
# So the image mirrors the repo's shape:
#
#     /app/store-config.json        <- parents[2]
#     /app/backend/app/store.py
#
# Preserving the layout rather than making the path configurable means the logic
# that works in development works here for the same reason, instead of by a
# second arrangement someone has to remember to keep in step.

# The target architecture is set by `--platform linux/amd64` on the BUILD
# COMMAND, not pinned here: a constant in FROM makes the Dockerfile unusable for
# any other platform and buildx warns about it (FromPlatformFlagConstDisallowed).
#
# amd64 because this machine is x86 and Fargate defaults to it. Getting it wrong
# produces `exec format error` -- a task that starts, dies, and restarts forever,
# with nothing in the logs to say why. Verify with:
#
#     docker image inspect manitou-api:local --format '{{.Os}}/{{.Architecture}}'
FROM python:3.12-slim

# Debian slim, NOT Alpine. Every wheel this project needs -- psycopg2-binary,
# pillow, bcrypt, uvloop, httptools -- ships as manylinux, which Alpine's musl
# libc cannot use. Alpine would compile them from source, need a toolchain the
# image then carries, and end up larger and far slower to build than the thing it
# was meant to beat.
#
# 3.12 matches the development venv (3.12.3). A different major would mean the
# tests passing against one interpreter and production running another.

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# PYTHONUNBUFFERED matters more than it looks: Python block-buffers stdout when
# it is not a TTY, so without this CloudWatch shows nothing until the buffer
# fills -- and a task killed mid-buffer loses its last logs entirely, which are
# exactly the ones that would say why it died.

# Debian security updates published since the base image was built.
#
# Measured, not assumed: the first ECR scan reported 28 findings (4 CRITICAL,
# 15 HIGH), all OS packages -- perl, openssl, glibc, gzip, sqlite3 -- and none
# from requirements.txt. Adding this layer took it to 18 (4 CRITICAL, 8 HIGH).
#
# The 4 CRITICALs survive because Debian has not shipped fixes for them: 3 in
# perl and 1 in glibc. perl-base is marked `Essential: yes, Priority: required`,
# and nothing in this application invokes perl -- so it is carried deliberately.
# Ripping out an Essential package to move a scanner number is a worse trade than
# an unreachable CVE. Revisit with a distroless base in Phase 8 if it matters.
#
# A base image is a point-in-time snapshot; CVEs are disclosed continuously, so
# an image that never upgrades accumulates them by standing still.
#
# The trade is reproducibility: this pulls whatever Debian ships today, so two
# builds of the same commit can differ. Accepted, because the alternative is
# shipping known-critical libc. Pin the base image by digest and rebuild on
# upstream releases if reproducibility ever matters more.
#
# --no-install-recommends and the apt list cleanup in the same layer, so the
# package index never lands in the image.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# A real user, not root. Created before the copies so the layer is cached.
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app/backend

# Dependencies first, application second. Editing a router must not reinstall
# SQLAlchemy -- pip only re-runs when requirements.txt itself changes.
#
# requirements.txt ALONE, per CLAUDE.md: the production container never ships
# pytest or the test client. requirements-dev.txt is not copied at all.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# store-config.json lands at /app -- which is parents[2] from /app/backend/app.
COPY store-config.json /app/store-config.json
COPY backend/ /app/backend/

# Everything the app owns, owned by the user that runs it.
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# python rather than curl: slim has no curl, and installing one for a health
# check is a package to patch for the life of the image. urllib is stdlib.
#
# Note this probe hits /health, which executes SELECT 1 -- so an unreachable
# database marks the container unhealthy. That is the intended reading: an API
# that cannot serve a query is not healthy just because its process is alive.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# --host 0.0.0.0, not the default 127.0.0.1. A container binding loopback is
# unreachable from outside itself, and the symptom is a process that starts
# cleanly and answers nothing -- the most common containerisation mistake there
# is.
#
# Exec form (a JSON array), so uvicorn is PID 1 and receives SIGTERM directly.
# The shell form would put /bin/sh at PID 1, which does not forward signals, and
# ECS would wait out its full stop timeout before killing the task on every
# deploy.
#
# No --workers: Express Mode scales by running more tasks, so one process per
# container keeps the scaling unit a task rather than a hidden pool inside one.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
