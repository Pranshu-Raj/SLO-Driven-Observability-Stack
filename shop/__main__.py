import asyncio
import sys

import uvicorn

from shop import config, log

SERVICES = ("api", "frontend", "worker")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in SERVICES:
        sys.exit(f"usage: python -m shop {{{'|'.join(SERVICES)}}}")

    service = sys.argv[1]
    log.setup(service)
    settings = config.load(service)

    if service == "worker":
        from shop.worker.consumer import main as run_worker

        asyncio.run(run_worker(settings))
        return

    if service == "api":
        from shop.api.app import create_app
    else:
        from shop.frontend.app import create_app

    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",
        port=settings.port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
