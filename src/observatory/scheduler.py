"""APScheduler orchestration: every pipeline on its schedule, one process.

All times UTC. Single-worker executor runs jobs strictly one at a time
(the embedding model is not guaranteed thread-safe, and serialized jobs
give readable logs). Collectors are idempotent, so catch-up runs after
laptop sleep are safe by construction.

Run:  python -m observatory.scheduler          # wait for scheduled times
      python -m observatory.scheduler --kick   # also run every job once now
"""

import logging
import socket
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from observatory.infra.logging_setup import setup_logging
from observatory.ingest.apod import fetch_apod
from observatory.ingest.arxiv import fetch_arxiv_papers
from observatory.ingest.rss import fetch_all_feeds
from observatory.ingest.swpc import fetch_all_space_weather
from observatory.journal.generate import generate_issue, save_html
from observatory.rag.indexer import index_documents

logger = logging.getLogger(__name__)

UTC = timezone.utc


def run_arxiv() -> None:
    fetch_arxiv_papers(pages=2)


def run_journal() -> None:
    """Generate the weekly issue and render it to output/."""
    result = generate_issue()
    if result is None:
        logger.error("Journal generation failed; will try again next Sunday")
        return
    path = save_html(result)
    logger.info("Journal issue saved to %s", path)


# (name, function, trigger, misfire_grace_time)
# grace=None: always catch up after sleep, however late (collectors/indexer —
# idempotent, a late run just picks up whatever is new).
# The journal instead gets a 6h grace window: a Sunday issue that was missed
# entirely should not silently appear mid-week; rerun via --kick if wanted.
JOBS = [
    ("apod", fetch_apod, CronTrigger(hour=6, minute=0, timezone=UTC), None),
    ("rss", fetch_all_feeds, CronTrigger(hour="*/2", minute=5, timezone=UTC), None),
    ("arxiv", run_arxiv, CronTrigger(hour=7, minute=0, timezone=UTC), None),
    ("swpc", fetch_all_space_weather, CronTrigger(minute="*/30", timezone=UTC), None),
    ("indexer", index_documents, CronTrigger(minute=15, timezone=UTC), None),
    # The journal is scheduled in the owner's local timezone (Saturday morning
    # coffee time in Toronto), unlike the data collectors which stay on UTC.
    ("journal", run_journal, CronTrigger(day_of_week="sat", hour=10, minute=0, timezone=ZoneInfo("America/Toronto")), 6 * 3600),
]


def build_scheduler(kick: bool = False) -> BlockingScheduler:
    scheduler = BlockingScheduler(
        timezone=UTC,
        executors={"default": ThreadPoolExecutor(max_workers=1)},
        job_defaults={"coalesce": True, "max_instances": 1},
    )
    for name, func, trigger, grace in JOBS:
        # NB: passing next_run_time=None would PAUSE the job in APScheduler 3.x,
        # so the kwarg is only supplied in kick mode.
        extra = {"next_run_time": datetime.now(UTC)} if kick else {}
        scheduler.add_job(
            func,
            trigger,
            id=name,
            name=name,
            misfire_grace_time=grace,
            **extra,
        )
    return scheduler


def main() -> int:
    setup_logging()
    # feedparser has no timeout parameter; a stalled feed would block the
    # single worker forever without a process-wide socket timeout.
    socket.setdefaulttimeout(30)

    kick = "--kick" in sys.argv
    scheduler = build_scheduler(kick=kick)
    now = datetime.now(UTC)
    for name, _, trigger, _ in JOBS:
        # Jobs are pending until start(), so compute the next fire time
        # from the trigger directly for the startup log.
        logger.info("Scheduled %-8s next run %s", name, trigger.get_next_fire_time(None, now))
    if kick:
        logger.info("Kick mode: every job will run once now, then follow its schedule")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
