from collections import defaultdict

from elements.series_type import SeriesType


class Team:
    def __init__(self, division=None):
        self.id = 0
        self.division = division
        self.name = None
        self.schedule = []
        self.series_by_divisional_opponent = defaultdict(list)
        self.series_by_subleague_opponent = defaultdict(list)
        self.series_by_interleague_opponent = defaultdict(list)
        self.series_by_opponent = [self.series_by_divisional_opponent, self.series_by_subleague_opponent,
                                   self.series_by_interleague_opponent]
        if division is not None:
            division.teams.append(self)

    def get_games(self, s):
        return [g for d in s.schedule for g in d.games_today if g.home is self or g.away is self]

    def get_games_against_team(self, s, o):
        return [g for g in self.get_games(s) if g.home is o or g.away is o]

    def get_games_against_pool(self, s, p):
        return [g for g in self.get_games(s) if g.home in p.teams and g.away in p.teams and p.type == g.type]

    def get_home_games_against_pool(self, s, p):
        return [g for g in self.get_games_against_pool(s, p) if g.home is self]

    def get_away_games_against_pool(self, s, p):
        return [g for g in self.get_games_against_pool(s, p) if g.away is self]

    def get_home_games(self, s):
        return [g for g in self.get_games(s) if g.home is self]

    def get_away_games(self, s):
        return [g for g in self.get_games(s) if g.away is self]

    def get_home_games_against(self, s, series_type, o):
        return [g for g in self.get_games_against_team(s, o) if g.home is self and g.type == series_type]

    def get_away_games_against(self, s, series_type, o):
        return [g for g in self.get_games_against_team(s, o) if g.away is self and g.type == series_type]

    def get_opponent_teams(self, series_type=None):
        if series_type is None:
            return [t for opponent_map in self.series_by_opponent for t in opponent_map]
        # The original collected into a set; a dict keeps the order stable.
        teams = {}
        for opponent_map in self.series_by_opponent:
            for opponent, series in opponent_map.items():
                if any(s.type == series_type for s in series):
                    teams[opponent] = True
        return list(teams)

    def get_home_series_against(self, schedule, o):
        return [s for opponent_map in self.series_by_opponent for opponent, series in opponent_map.items()
                if opponent is o for s in series if s.games[0].home is self]

    def get_away_series_against(self, schedule, o):
        return [s for opponent_map in self.series_by_opponent for opponent, series in opponent_map.items()
                if opponent is o for s in series if s.games[0].away is self]

    def put_series(self, s):
        if s.type == SeriesType.DIVISIONAL:
            self._add_series(self.series_by_divisional_opponent, s)
        elif s.type == SeriesType.SUBLEAGUE:
            self._add_series(self.series_by_subleague_opponent, s)
        elif s.type == SeriesType.INTERLEAGUE:
            self._add_series(self.series_by_interleague_opponent, s)

    def _add_series(self, series_map, s):
        other_team = s.t2 if s.t1 is self else s.t1
        series_map[other_team].append(s)

    def get_all_series(self):
        return [s for opponent_map in self.series_by_opponent for series in opponent_map.values() for s in series]

    def get_all_series_against(self, t):
        return [s for opponent_map in self.series_by_opponent for opponent, series in opponent_map.items()
                if opponent is t for s in series]

    def __str__(self):
        return "T" + str(self.id)

    __repr__ = __str__

    def print_schedule(self, schedule):
        for g in self.get_games(schedule):
            home = g.home is self
            other = g.away if home else g.home
            print(str(g.day) + " " + str(self) + " " + ("vs" if home else "at") + " " + str(other) + "   ")
        print("")

    def print_schedule_summary(self, schedule):
        totals = {"home": 0, "away": 0}
        # Per series type: [home games, away games, games by opponent id, home by id, away by id]
        by_type = {t: [0, 0, defaultdict(int), defaultdict(int), defaultdict(int)]
                   for t in (SeriesType.DIVISIONAL, SeriesType.SUBLEAGUE, SeriesType.INTERLEAGUE)}

        for g in self.get_games(schedule):
            if g.home is None or g.away is None:
                continue
            home = g.home.id == self.id
            opponent = g.away if home else g.home
            oid = opponent.id
            totals["home" if home else "away"] += 1

            if g.type in by_type:
                counts = by_type[g.type]
                counts[2][oid] += 1
                if home:
                    counts[3][oid] += 1
                    counts[0] += 1
                else:
                    counts[4][oid] += 1
                    counts[1] += 1

        print("T" + str(self.id) + " schedule debug " + str(totals["home"] + totals["away"]) + " games "
              + str(totals["home"]) + "H/" + str(totals["away"]) + "A")
        for label, series_type in (("Divisional", SeriesType.DIVISIONAL), ("Subleague", SeriesType.SUBLEAGUE),
                                   ("Interleague", SeriesType.INTERLEAGUE)):
            home_games, away_games, total, home_by_id, away_by_id = by_type[series_type]
            print(label + " " + str(home_games + away_games) + " games " + str(home_games) + "H/" + str(away_games) + "A")
            for key, value in total.items():
                print("\tT" + str(key) + " " + str(value) + " games " + str(home_by_id[key]) + "H/"
                      + str(away_by_id[key]) + "A")
        print("")
