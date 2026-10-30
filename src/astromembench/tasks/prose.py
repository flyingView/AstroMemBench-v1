"""Read the published prose without consulting authored event/fact fields.

Template reference readers use these helpers while the history presentation is
being migrated. They parse task evidence, never participant answers or scores.
"""
import re


STORY_STAMP = r'任务第\d+日\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?'


def paragraphs(history):
    """Yield all public paragraphs in delivery order, including background."""
    for packet in history:
        yield from record_paragraphs(packet['data']['records'])


def record_paragraphs(records):
    """Read the same prose contract from history or newly delivered receipts."""
    for record in records:
        yield from record['text'].split('\n\n')


def microseconds(stamp):
    """Parse the exact printed story clock without a float or second rounding."""
    match = re.fullmatch(r'任务第(\d+)日(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?', stamp)
    if match is None:
        raise ValueError('Expected an exact printed story timestamp')
    day, hour, minute, second = map(int, match.groups()[:4])
    if hour >= 24 or minute >= 60 or second >= 60:
        raise ValueError('Invalid printed story clock')
    fraction = int((match[5] or '').ljust(6, '0'))
    return ((day * 24 + hour) * 3600 + minute * 60 + second) * 1_000_000 + fraction


def seconds(stamp):
    """Read a whole-second model clock without silently rounding a fraction."""
    value = microseconds(stamp)
    if value % 1_000_000:
        raise ValueError('Expected a whole-second story timestamp')
    return value // 1_000_000
