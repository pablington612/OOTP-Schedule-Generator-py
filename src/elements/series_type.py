from enum import Enum

from elements.day_type import DayType

# Same values as Scheduler.INDEX_*; repeated here to avoid a circular import.
_INDEX_DIVISIONAL = 0
_INDEX_SUBLEAGUE = 1
_INDEX_INTERLEAGUE = 2


class SeriesType(Enum):
    BREAK = "BREAK"
    INTERLEAGUE = "INTERLEAGUE"
    SUBLEAGUE = "SUBLEAGUE"
    DIVISIONAL = "DIVISIONAL"
    ALLSTAR = "ALLSTAR"
    UNSET = "UNSET"

    def requires_schedule_entry(self):
        return self in (SeriesType.INTERLEAGUE, SeriesType.SUBLEAGUE, SeriesType.DIVISIONAL)

    @staticmethod
    def for_index(i):
        if i == _INDEX_DIVISIONAL:
            return SeriesType.DIVISIONAL
        if i == _INDEX_SUBLEAGUE:
            return SeriesType.SUBLEAGUE
        if i == _INDEX_INTERLEAGUE:
            return SeriesType.INTERLEAGUE
        raise ValueError(i)

    def index(self):
        if self == SeriesType.INTERLEAGUE:
            return _INDEX_INTERLEAGUE
        if self == SeriesType.SUBLEAGUE:
            return _INDEX_SUBLEAGUE
        if self == SeriesType.DIVISIONAL:
            return _INDEX_DIVISIONAL
        return -1

    @staticmethod
    def get_series_type_for_day_type(day_type):
        return {
            DayType.BREAK: SeriesType.BREAK,
            DayType.ALLSTAR: SeriesType.ALLSTAR,
            DayType.INTERLEAGUE: SeriesType.INTERLEAGUE,
            DayType.DIVISIONAL: SeriesType.DIVISIONAL,
            DayType.SUBLEAGUE: SeriesType.SUBLEAGUE,
        }.get(day_type, SeriesType.UNSET)

    def __str__(self):
        return self.name

    __repr__ = __str__
