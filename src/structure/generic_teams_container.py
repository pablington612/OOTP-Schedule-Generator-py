class GenericTeamsContainer:
    """A copy of another container's team list (a Division, Subleague, ...)."""

    def __init__(self, parent, teams):
        self.parent = parent
        self.teams = list(teams)

    def get_teams(self):
        return self.teams

    def size(self):
        return len(self.teams)

    def __str__(self):
        return "GC: " + str(self.teams)

    __repr__ = __str__
