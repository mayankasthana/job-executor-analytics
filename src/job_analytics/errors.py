"""Exception hierarchy for job_analytics.

Callers (the CLI, embedding applications) can catch :class:`JobAnalyticsError`
to handle any failure this package raises deliberately.
"""


class JobAnalyticsError(Exception):
    """Base class for errors raised deliberately by job_analytics."""


class RecordValidationError(JobAnalyticsError, ValueError):
    """A single raw record failed validation.

    The message is user-facing: it names the offending field where possible.
    """


class InputFileError(JobAnalyticsError):
    """The input file could not be read or parsed as JSON."""
