"""Send N concurrent requests to a URL and summarise the status codes.

Runs from the LAPTOP, not inside the VPC -- it talks to the public ALB.

    backend/.venv/bin/python infra/probes/burst.py <url> [concurrency]

**Why concurrency is the whole point.** A stale database password does not
break a request; it breaks a *new connection*. One request at a time reuses the
single pooled connection the health check keeps warm, so a sequential probe
returns 200 and reports that everything is fine. Only enough simultaneous
requests to exhaust the warm connections force the pool to open new ones, which
is where the failure lives.

The API's pool holds 5 + 10 overflow per task, so the default of 20 here is
deliberately above that ceiling.
"""

import sys
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

URL = sys.argv[1] if len(sys.argv) > 1 else sys.exit(__doc__)
N = int(sys.argv[2]) if len(sys.argv) > 2 else 20


def one(_):
    try:
        with urllib.request.urlopen(URL, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:  # noqa: BLE001 - a timeout is a result, not a crash
        return type(e).__name__


with ThreadPoolExecutor(max_workers=N) as pool:
    codes = Counter(pool.map(one, range(N)))

print(f"  {URL}  x{N} concurrent")
for code, count in sorted(codes.items(), key=lambda kv: str(kv[0])):
    print(f"    {code}: {count}")
