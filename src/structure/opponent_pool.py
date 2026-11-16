from elements.series_type import SeriesType


class OpponentPool:
    def __init__(self):
        self.type = SeriesType.UNSET
        self.teams = []
        self.byes = []

    def __str__(self):
        return str(self.type) + " " + str(len(self.teams)) + " pool"

    __repr__ = __str__

    def size(self):
        return len(self.teams)
