class Division:
    def __init__(self, sl):
        self.id = 0
        self.subleague = sl
        self.name = None
        self.teams = []
        self.divisional_pool_count = 1
        sl.divisions.append(self)

    def get_divisional_opponents_for(self, t):
        return [opponent for opponent in self.teams if opponent.id != t.id]

    def get_teams(self):
        return self.teams

    def size(self):
        return len(self.teams)

    def __str__(self):
        return "D" + str(self.id) + ": " + str(self.teams)

    __repr__ = __str__
