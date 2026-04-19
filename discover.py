from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


DATA_DIR = Path("data")
DISCOVERED_URLS_PATH = DATA_DIR / "discovered_urls.json"
USER_AGENT = "VantionDemoBot/1.0 (+https://vantion.com/demo)"


# Official program pages or official FAQ pages for real pre-college programs.
# Add URLs here to extend the demo without changing the rest of the pipeline.
SEED_URLS = [
    "https://spcs.stanford.edu/programs/stanford-pre-collegiate-summer-institutes",
    "https://spcs.stanford.edu/programs/stanford-pre-collegiate-university-level-online-math-physics",
    "https://www.cmu.edu/pre-college/academic-programs/summer-session.html",
    "https://www.cmu.edu/pre-college/academic-programs/computer-science-scholars.html",
    "https://bwsi.mit.edu/apply-now/",
    "https://girlswhocode.com/programs/pathways",
    "https://precollege.berkeley.edu/summer-computer-science-academy",
    "https://k12stem.engineering.nyu.edu/programs/arise",
]


def discover_program_urls(extra_urls: list[str] | None = None) -> list[str]:
    """Return a deduplicated URL list and save it for the extraction step."""
    logger.info("Starting URL discovery process")
    DATA_DIR.mkdir(exist_ok=True)
    urls = [*SEED_URLS, *(extra_urls or [])]
    deduped = list(dict.fromkeys(url.strip() for url in urls if url.strip()))
    logger.info(f"Discovered and deduplicated {len(deduped)} program URLs")
    DISCOVERED_URLS_PATH.write_text(json.dumps(deduped, indent=2), encoding="utf-8")
    logger.info(f"Saved discovered URLs to {DISCOVERED_URLS_PATH}")
    return deduped


def can_fetch(url: str, user_agent: str = USER_AGENT) -> bool:
    """Check robots.txt for the demo crawler user agent."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception:
        # Demo-friendly fallback: if robots.txt cannot be read, let requests
        # surface any real fetch problem in polite_get.
        return True
    return parser.can_fetch(user_agent, url)


def polite_get(
    url: str,
    session: Any = None,
    min_delay: float = 0.8,
    max_delay: float = 2.0,
    user_agent: str = USER_AGENT,
) -> Any:
    """Fetch one URL politely: robots.txt check, jitter, user agent, status check."""
    import requests

    if not can_fetch(url, user_agent=user_agent):
        raise RuntimeError(f"Blocked by robots.txt: {url}")

    time.sleep(random.uniform(min_delay, max_delay))
    client = session or requests
    response = client.get(url, timeout=15, headers={"User-Agent": user_agent})
    response.raise_for_status()
    return response


def discover(seed_urls: list[str] | None = None, out_path: str = "data/discovered_urls.json") -> dict:
    """Polite discovery pass that records fetch status for each seed URL."""
    seed_urls = seed_urls or SEED_URLS
    results = []
    successes = 0
    failures = 0

    for url in seed_urls:
        try:
            response = polite_get(url)
            results.append({"url": url, "status_code": response.status_code})
            successes += 1
        except Exception as exc:
            results.append({"url": url, "status_code": None, "error": str(exc)})
            failures += 1

    output = {
        "total": len(seed_urls),
        "successes": successes,
        "failures": failures,
        "results": results,
    }
    output_path = Path(out_path)
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Discovered {len(seed_urls)} URLs: {successes} success, {failures} failures")
    return output


if __name__ == "__main__":
    discover()
