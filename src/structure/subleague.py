class Subleague:
    def __init__(self, league):
        self.id = 0
        self.league = league
        self.name = None
        self.divisions = []
        league.subleagues.append(self)

    def get_divisions(self):
        return self.divisions

    def get_teams(self):
        return [t for d in self.divisions for t in d.get_teams()]

    def size(self):
        return len(self.get_teams())

    def __str__(self):
        return "SL" + str(self.id) + ": " + str(self.divisions)

    __repr__ = __str__
