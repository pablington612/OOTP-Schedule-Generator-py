def _jstr(o):
    return "null" if o is None else str(o)


class Game:
    def __init__(self):
        self.parent = None
        self.type = None
        self.home = None
        self.away = None
        self.day = None
        self.time = 0

    def __eq__(self, o):
        if not isinstance(o, Game):
            return False
        return (self.type == o.type and self.home is o.home and self.away is o.away
                and self.day is o.day and self.time == o.time)

    # The original overrides equals() but not hashCode(), so hashing stays identity-based.
    __hash__ = object.__hash__

    def get_other_team(self, t):
        if self.home is t:
            return self.away
        if self.away is t:
            return self.home
        return None

    def __str__(self):
        return (_jstr(self.type) + " game " + _jstr(self.home) + " vs. " + _jstr(self.away)
                + " " + _jstr(self.day) + ":" + str(self.time))

    __repr__ = __str__
