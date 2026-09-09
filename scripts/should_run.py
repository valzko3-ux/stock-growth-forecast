"""
Zeitfenster-Wächter für den GitHub-Actions-Workflow.

Der Workflow wird per Cron in zwei UTC-Fenstern getriggert (die zusammen
sowohl CET- als auch CEST-Offsets abdecken), aber die eigentliche Pipeline
soll nur exakt um 07:30 und 15:30 Europe/Berlin-Zeit laufen -- DST-sicher,
weil hier die echte Zeitzone (zoneinfo) statt eines festen UTC-Offsets
ausgewertet wird. Bei manuellem Trigger (workflow_dispatch) läuft es immer.
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

TARGETS = {(7, 30), (15, 30)}
TOLERANCE_MIN = 5


def main():
    manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    now_berlin = datetime.now(ZoneInfo("Europe/Berlin"))
    should_run = manual or any(
        now_berlin.hour == h and abs(now_berlin.minute - m) <= TOLERANCE_MIN
        for h, m in TARGETS
    )
    print(f"Berlin-Zeit: {now_berlin:%Y-%m-%d %H:%M %Z} -> run={should_run}")

    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"run={'true' if should_run else 'false'}\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
