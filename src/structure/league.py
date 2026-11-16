from structure.team import Team

# Same values as Scheduler.INDEX_*; repeated here to avoid a circular import.
_INDEX_DIVISIONAL = 0
_INDEX_SUBLEAGUE = 1
_INDEX_INTERLEAGUE = 2


class League:
    def __init__(self):
        self.id = 0
        self.name = None
        self.subleagues = []
        self.divisional_pools = []
        self.subleague_pools = []
        self.interleague_pools = []
        self.interleague_pool_count = 1
        self.all_star1 = Team()
        self.all_star2 = Team()

    def pools_by_index(self, priority):
        if priority == _INDEX_DIVISIONAL:
            return self.divisional_pools
        if priority == _INDEX_SUBLEAGUE:
            return self.subleague_pools
        if priority == _INDEX_INTERLEAGUE:
            return self.interleague_pools
        return None

    def all_pools(self):
        return self.divisional_pools + self.subleague_pools + self.interleague_pools

    def get_subleagues(self):
        return self.subleagues

    def get_divisions(self):
        return [d for s in self.subleagues for d in s.get_divisions()]

    def get_allstar_teams(self):
        self.all_star1.id = -1
        self.all_star2.id = -2
        return [self.all_star1, self.all_star2]

    def get_teams(self):
        return [t for s in self.subleagues for t in s.get_teams()]

    def size(self):
        return len(self.get_teams())

    def __str__(self):
        return "L" + str(self.id) + ": " + str(self.subleagues)

    __repr__ = __str__

    def get_interleague_divisions_for(self, division):
        return [potential for potential in self.get_divisions() if potential.subleague is not division.subleague]
