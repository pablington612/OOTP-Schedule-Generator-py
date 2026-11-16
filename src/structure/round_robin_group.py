import random
from decimal import Decimal
from enum import Enum

import groovy_math
from elements.game import Game
from elements.series import Series


class RoundRobinGroup:
    class Type(Enum):
        SUBLEAGUE = "SUBLEAGUE"
        INTERLEAGUE = "INTERLEAGUE"

    def __init__(self, pool, category_cycle_time):
        self.right_home = False
        self.outside_team = None
        self.left_column = []
        self.right_column = []
        self.category_cycle_time = category_cycle_time
        self.category_slots_filled = Decimal(0)
        self.own_slots_filled = Decimal(0)
        self.pool = pool
        pool_size = len(pool.teams)
        self.has_bye = pool_size % 2 == 1

        if self.has_bye:
            self.own_cycle_time = groovy_math.div(pool_size, pool_size - 1)
        else:
            self.own_cycle_time = Decimal(1)

        if pool_size == 2:
            self.right_column = [pool.teams[0]]
            self.left_column = [pool.teams[1]]
            return

        self._construct_standard_pool()

    def _construct_standard_pool(self):
        pool_size = len(self.pool.teams)
        shuffled_teams = list(self.pool.teams)
        random.shuffle(shuffled_teams)

        first_half = pool_size // 2
        if self.has_bye:
            first_half += 1
        self.left_column.extend(shuffled_teams[:first_half])

        second_half = pool_size
        if not self.has_bye:
            second_half = pool_size - 1
            self.outside_team = shuffled_teams[pool_size - 1]
        self.right_column.extend(shuffled_teams[first_half:second_half])

    def get_matchups(self):
        games = []
        for i in range(len(self.right_column)):
            g = Game()
            if self.right_home:
                g.home = self.right_column[i]
                g.away = self.left_column[i]
            else:
                g.home = self.left_column[i]
                g.away = self.right_column[i]
            games.append(g)

        if not self.has_bye and self.size() > 2:
            g = Game()
            inside_team = self.left_column[-1]
            if self.right_home:
                g.home = inside_team
                g.away = self.outside_team
            else:
                g.home = self.outside_team
                g.away = inside_team
            games.append(g)
        return games

    def rotate(self):
        self.right_home = not self.right_home
        if self.size() > 2:
            self.left_column.insert(0, self.right_column.pop(0))
            self.right_column.append(self.left_column.pop())

    def __str__(self):
        outside = "null" if self.outside_team is None else str(self.outside_team)
        return "Outside: " + outside + " Left column: " + str(self.left_column) + " Right column: " + str(self.right_column)

    def matchup_count_for_rounds(self, rounds):
        return self.size() * rounds - rounds

    def size(self):
        return self.pool.size()

    def copy_series(self, destination, template):
        if self.category_cycle_time > 1:
            if self.category_slots_filled - self.own_slots_filled >= 1:
                self.category_slots_filled = Decimal(0)
                self.own_slots_filled = Decimal(0)
                return False

        self._copy_matchups(destination, template)

        self.own_slots_filled = self.own_slots_filled + self.own_cycle_time
        self.category_slots_filled = self.category_slots_filled + self.category_cycle_time
        return True

    def _copy_matchups(self, destination, template):
        """Copies the template series into destination once per current matchup."""
        for matchup in self.get_matchups():
            copy = Series()
            copy.t1 = matchup.home
            copy.t2 = matchup.away
            copy.start_day = template.start_day
            copy.end_day = template.end_day
            copy.length = template.length
            copy.type = template.type

            for g in template.games:
                game = Game()
                game.day = destination.schedule[g.day.get_index()]
                game.home = matchup.home
                game.away = matchup.away
                game.parent = copy
                game.type = template.type
                copy.games.append(game)
                day = game.day
                day.games_today.append(game)
                day.series_ongoing_today.append(copy)
                if game.home not in day.teams_playing_today:
                    day.teams_playing_today.append(game.home)
                if game.away not in day.teams_playing_today:
                    day.teams_playing_today.append(game.away)
                destination.total_games_scheduled += 1

            start_day = destination.schedule[template.start_day - 1]
            start_day.series_starting_today.append(copy)
            destination.total_series_scheduled += 1
            copy.t1.put_series(copy)
            copy.t2.put_series(copy)
