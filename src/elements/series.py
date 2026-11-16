from elements.series_type import SeriesType

_LETTERS = {SeriesType.INTERLEAGUE: "I", SeriesType.SUBLEAGUE: "S", SeriesType.DIVISIONAL: "D", SeriesType.UNSET: "U"}


class Series:
    def __init__(self):
        self.type = SeriesType.UNSET
        self.t1 = None
        self.t2 = None
        self.length = 0
        self.start_day = 0
        self.end_day = 0
        self.games = []

    def __str__(self):
        if self.type == SeriesType.BREAK:
            return "Break"
        if self.type in _LETTERS:
            return str(self.length) + _LETTERS[self.type] + " series " + str(self.t1) + "v" + str(self.t2)
        return str(self.length) + "-game series"

    __repr__ = __str__
