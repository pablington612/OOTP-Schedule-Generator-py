from enum import Enum


class DayType(Enum):
    NORMAL = "NORMAL"
    BREAK = "BREAK"
    ALLSTAR = "ALLSTAR"
    DIVISIONAL = "DIVISIONAL"
    SUBLEAGUE = "SUBLEAGUE"
    INTERLEAGUE = "INTERLEAGUE"

    def is_calendar_type(self):
        return self in (DayType.DIVISIONAL, DayType.SUBLEAGUE, DayType.INTERLEAGUE)

    def __str__(self):
        return self.name

    __repr__ = __str__
