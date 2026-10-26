"""Enables ``python -m job_analytics``."""

import sys

from job_analytics.cli import main

if __name__ == "__main__":
    sys.exit(main())
