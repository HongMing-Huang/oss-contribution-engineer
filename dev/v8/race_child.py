#!/usr/bin/env python3
"""race_child.py — one round of the click#3802 race window (V8 fixture).

Schedules SIGINT to itself ~0.12 s in, landing while click.prompt() waits on
stdin; prints nothing special — the parent inspects stderr for an unhandled
KeyboardInterrupt traceback originating inside click/.

Usage: python3 race_child.py <click_repo_root>
"""

import os
import signal
import sys
import threading
import time

sys.path.insert(0, sys.argv[1].rstrip("/") + "/src")


def fire():
    time.sleep(0.12)
    os.kill(os.getpid(), signal.SIGINT)


threading.Thread(target=fire, daemon=True).start()

import click  # noqa: E402

click.prompt("continue?", default="y")
