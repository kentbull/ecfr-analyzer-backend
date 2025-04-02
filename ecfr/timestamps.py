import datetime


def nowUTC() -> datetime.datetime:
    """
    Returns timezone aware datetime of current UTC time
    Convenience function that allows monkeypatching in tests to mock time
    """
    return datetime.datetime.now(datetime.timezone.utc)

def nowIso8601():
    """
    Returns time now in RFC-3339 profile of ISO 8601 format.
    use now(timezone.utc)

    YYYY-MM-DDTHH:MM:SS.ffffff+HH:MM[:SS[.ffffff]]
    .strftime('%Y-%m-%dT%H:%M:%S.%f%z')
    '2020-08-22T17:50:09.988921+00:00'
    Assumes TZ aware
    For nanosecond use instead attotime or datatime64 in pandas or numpy
    """
    return nowUTC().isoformat(timespec="microseconds")