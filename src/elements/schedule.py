import random

import scheduler as scheduler_module
from elements.day import Day
from elements.day_type import DayType
from elements.game import Game
from elements.series_type import SeriesType
from math_util import jdiv, jmod


class Schedule:
    def __init__(self):
        self.DEBUG = False
        self.total_series_scheduled = 0
        self.total_games_scheduled = 0
        self.scheduler = None
        self.schedule = []
        self.success = False
        self.first_allstar_break_day_index = 0
        self.allstar_day = 0
        self.last_allstar_break_day_index = 0
        self.slot_conflicts = 0

    def initialize(self, scheduler, length, debug):
        self.scheduler = scheduler
        self.DEBUG = debug
        day_code = scheduler.start_day_of_week
        preferred_allstar_day = int(float(length) * (scheduler.allstar_percentage / 100.0))
        allstar_day_of_week = scheduler.allstar_day_of_week
        break_days_before_allstar_game = jdiv(scheduler.allstar_break_days, 2)
        break_days_after_allstar_game = jdiv(scheduler.allstar_break_days, 2)
        if scheduler.allstar_break_days % 2 == 0:
            break_days_before_allstar_game -= 1

        allstar_scheduled = scheduler.allstar_percentage < 0

        day_index = 0
        while day_index < length:
            d = Day()
            d.number = day_index + 1
            d.day_code = day_code
            if day_code != -1:
                if day_code in scheduler.off_days_of_week:
                    d.type = DayType.BREAK
                day_code = (day_code + 1) % 7

            if d.number < preferred_allstar_day or allstar_scheduled:
                self.schedule.append(d)
            elif ((allstar_day_of_week == -1
                   and jmod(d.number - break_days_before_allstar_game, scheduler.largest_preferred_series_length) == 1)
                  or (allstar_day_of_week != -1 and d.day_code == allstar_day_of_week)):
                if self.DEBUG:
                    print("Scheduling all-star game around " + str(d.number) + ".")

                d.type = DayType.ALLSTAR
                self.allstar_day = d.number
                g = Game()
                g.day = d
                allstar_teams = scheduler.league.get_allstar_teams()
                g.home = allstar_teams[0]
                g.away = allstar_teams[1]
                g.time = 1905
                g.type = SeriesType.ALLSTAR
                d.games_today.append(g)
                self.schedule.append(d)

                for j in range(1, break_days_before_allstar_game + 1):
                    # A negative index wraps to the end of the list, as in the original Groovy
                    # (all-star game in the first few days).
                    d = self.schedule[day_index - j]
                    d.type = DayType.BREAK

                for j in range(1, break_days_after_allstar_game + 1):
                    index = day_index + j
                    d = Day()
                    d.number = index + 1
                    d.day_code = day_code
                    d.type = DayType.BREAK
                    self.schedule.append(d)
                    if day_code != -1:
                        day_code = (day_code + 1) % 7

                self.first_allstar_break_day_index = self.allstar_day - break_days_before_allstar_game
                self.last_allstar_break_day_index = self.allstar_day + break_days_after_allstar_game
                if self.DEBUG:
                    print("Break days before: " + str(break_days_before_allstar_game)
                          + " First allstar day: " + str(self.first_allstar_break_day_index))
                if self.DEBUG:
                    print("Break days after: " + str(break_days_after_allstar_game)
                          + " Last allstar day: " + str(self.last_allstar_break_day_index))

                allstar_scheduled = True
                day_index += break_days_after_allstar_game
            else:
                self.schedule.append(d)
            day_index += 1

    def get_all_games(self):
        games = []
        for d in self.schedule:
            games.extend(d.games_today)
        return games

    def home_away_balance(self):
        Scheduler = scheduler_module.Scheduler
        series_swapped = 0
        print("Running initial balance pass...")
        for t in self.scheduler.league.get_teams():
            for i in range(Scheduler.INDEX_DIVISIONAL, Scheduler.INDEX_INTERLEAGUE + 1):
                series = t.series_by_opponent[i]
                series_type = SeriesType.for_index(i)
                for opponent in series.keys():
                    home_away_difference = (len(t.get_home_games_against(self, series_type, opponent))
                                            - len(t.get_away_games_against(self, series_type, opponent)))
                    # Series lengths may be floats (settings are parsed that way), so compare as float.
                    limit = -float(Scheduler.preferred_series_lengths[i]) * 2
                    while home_away_difference <= limit:
                        away_series = t.get_away_series_against(self, opponent)
                        random.shuffle(away_series)
                        for g in away_series[0].games:
                            g.home = t
                            g.away = opponent
                            home_away_difference += 2
                        series_swapped += 1

        print("Done. Swapped " + str(series_swapped) + " series.")
        print("Taking extra home games...")
        result = self._balance_pools_take_home_games()
        print("Done. Swapped " + str(result) + " series.")
        series_swapped += result
        print("Balancing finished: swapped H/A teams for " + str(series_swapped) + " series.")

    def _balance_pools_take_home_games(self):
        Scheduler = scheduler_module.Scheduler
        series_swapped = 0
        for pool in self.scheduler.league.all_pools():
            teams_above_500 = []
            teams_below_500 = []
            for t in pool.teams:
                if len(t.get_home_games_against_pool(self, pool)) > len(t.get_away_games_against_pool(self, pool)):
                    teams_above_500.append(t)
                elif len(t.get_away_games_against_pool(self, pool)) > len(t.get_home_games_against_pool(self, pool)):
                    teams_below_500.append(t)

            for t in teams_below_500:
                games_needed = len(t.get_away_games_against_pool(self, pool)) - len(t.get_home_games_against_pool(self, pool))

                for opponent in teams_above_500:
                    difference = (len(t.get_home_games_against(self, pool.type, opponent))
                                  - len(t.get_away_games_against(self, pool.type, opponent)))
                    series_length = float(Scheduler.preferred_series_lengths[pool.type.index()])
                    if difference <= -series_length:
                        away_series = t.get_away_series_against(self, opponent)
                        random.shuffle(away_series)
                        to_swap = next((s for s in away_series if s.type == pool.type), None)
                        if to_swap is None:
                            break

                        for g in to_swap.games:
                            g.home = t
                            g.away = opponent
                            difference += 2
                            games_needed -= 2
                        series_swapped += 1
                        if difference >= -series_length:
                            teams_above_500.remove(opponent)  # safe: the loop breaks right after
                        break

                while games_needed > 0:
                    progress = False
                    for donor in teams_above_500:
                        teams = self._get_common_opponents(t, pool.type, [donor])

                        def both_extra_home(passthrough):
                            extra_this_vs_passthrough_home = (
                                len(t.get_home_games_against(self, pool.type, passthrough))
                                - len(t.get_away_games_against(self, pool.type, passthrough)))
                            extra_passthrough_vs_donor_home = (
                                len(passthrough.get_home_games_against(self, pool.type, donor))
                                - len(passthrough.get_away_games_against(self, pool.type, donor)))
                            return extra_this_vs_passthrough_home > 0 and extra_passthrough_vs_donor_home > 0

                        teams = [p for p in teams if not both_extra_home(p)]
                        donor_games_above_500 = (len(donor.get_home_games_against_pool(self, pool))
                                                 - len(donor.get_away_games_against_pool(self, pool)))

                        if len(teams) > 0:
                            progress = True
                            random.shuffle(teams)
                            passthrough = teams[0]
                            home_series = donor.get_home_series_against(self, passthrough)
                            random.shuffle(home_series)
                            to_swap = next((s for s in home_series if s.type == pool.type), None)
                            if to_swap is None:
                                break

                            for g in to_swap.games:
                                g.home = passthrough
                                g.away = donor
                                donor_games_above_500 -= 2
                            series_swapped += 1
                            if donor_games_above_500 <= 0:
                                teams_above_500.remove(donor)  # safe: the loop breaks before its next iteration

                            home_series = passthrough.get_home_series_against(self, t)
                            random.shuffle(home_series)
                            to_swap = next((s for s in home_series if s.type == pool.type), None)
                            if to_swap is None:
                                break

                            for g in to_swap.games:
                                g.home = t
                                g.away = passthrough
                                games_needed -= 2
                            series_swapped += 1
                            break
                    if not progress:
                        break
        return series_swapped

    def move_breaks_to_end_of_series(self):
        for d in self.schedule:
            if d.type == DayType.BREAK and len(d.series_ongoing_today) > 0:
                first_allstar_day = self.first_allstar_break_day_index
                if first_allstar_day < self.allstar_day:
                    first_allstar_day += 1
                last_allstar_day = self.last_allstar_break_day_index
                if last_allstar_day > self.allstar_day + 1:
                    last_allstar_day -= 1

                if not (d.get_index() >= first_allstar_day) or not (d.get_index() <= last_allstar_day):
                    to_swap = d.series_ongoing_today[0]
                    last_game = None
                    first_game = None
                    non_off_days = self.scheduler.non_off_days_of_week
                    for g in to_swap.games:
                        # As in the original, the off-day check looks at the current best pick, not at g.
                        if ((last_game is None or g.day.get_index() > last_game.day.get_index())
                                and (last_game is None or last_game.day.day_code not in non_off_days)):
                            last_game = g
                        if ((first_game is None or g.day.get_index() < first_game.day.get_index())
                                and (first_game is None or first_game.day.day_code not in non_off_days)):
                            first_game = g

                    if last_game is not None or first_game is not None:
                        to_move = first_game if last_game is None else last_game
                        d.type = to_move.day.type
                        to_move.day.type = DayType.BREAK
                        move_start = False
                        if to_move.parent in to_move.day.series_starting_today:
                            move_start = True
                            to_move.day.series_starting_today.remove(to_move.parent)
                        to_move.day.series_ongoing_today = []
                        to_move.day = d
                        if move_start:
                            to_move.day.series_starting_today.append(to_move.parent)

    def get_run_starting_on(self, day_index):
        run_length = 0
        while (day_index < len(self.schedule)
               and self.schedule[day_index].type != DayType.BREAK
               and self.schedule[day_index].type != DayType.ALLSTAR):
            run_length += 1
            day_index += 1
        return run_length

    def _get_common_opponents(self, t, series_type, other_teams):
        other_teams_opponents = {}
        for other in other_teams:
            for o in other.get_opponent_teams(series_type):
                other_teams_opponents[o] = True
        own_opponents = t.get_opponent_teams(series_type)
        return [o for o in other_teams_opponents if o in own_opponents]

    def schedule_intraday(self):
        first = self.scheduler.first_start_time
        last = self.scheduler.last_start_time
        simultaneous = self.scheduler.simultaneous_games
        for d in self.schedule:
            games = list(d.games_today)
            random.shuffle(games)
            start_times = []
            if last == first:
                start_times = [first] * len(games)
            else:
                step = jdiv(last - first, max(jdiv(len(games), simultaneous), 1))
                i = first
                while i <= last:
                    hours = jdiv(i, 100)
                    minutes = jmod(jdiv(i, 10), 10)
                    difference_from_half_hour = abs(minutes - 5)
                    difference_from_prev_hour = abs(minutes - 0)
                    difference_from_next_hour = abs(minutes - 10)
                    if (difference_from_half_hour < difference_from_prev_hour
                            and difference_from_half_hour < difference_from_next_hour):
                        minutes = 30
                    elif (difference_from_next_hour < difference_from_half_hour
                          and difference_from_next_hour < difference_from_prev_hour):
                        hours += 1
                        minutes = 0
                    elif (difference_from_prev_hour <= difference_from_half_hour
                          and difference_from_prev_hour <= difference_from_next_hour):
                        minutes = 0
                    for _ in range(simultaneous):
                        start_times.append(hours * 100 + minutes + self.scheduler.start_offset)
                    i += step

            for g in games:
                # Groovy 2.4's List.pop() removes the last element.
                g.time = start_times.pop()

    def get_last_day(self):
        last_day = 0
        for d in self.schedule:
            if d.teams_playing_today:
                last_day = d.number
        return last_day

    @staticmethod
    def _format_time(time):
        return "0" + str(time) if time < 1000 else str(time)

    def print_schedule_by_day(self):
        last_day = self.get_last_day()
        for d in self.schedule:
            if d.number > last_day:
                break
            print("Day " + str(d.number))
            if d.type == DayType.BREAK:
                print("Break")
            elif d.type == DayType.DIVISIONAL:
                print("Divisional")
            elif d.type == DayType.SUBLEAGUE:
                print("Subleague")
            elif d.type == DayType.INTERLEAGUE:
                print("Interleague")
            else:
                for s in d.series_ongoing_today:
                    for g in s.games:
                        if g.day is d:
                            print("\t", end="")
                            if g.type == SeriesType.ALLSTAR:
                                print("All-star game @ " + self._format_time(g.time))
                            else:
                                print(str(g.home) + " vs " + str(g.away) + " @ " + self._format_time(g.time))
            print("")

    def print_schedule_grid(self):
        start_padding = 6
        first_line = "      "
        for t in self.scheduler.league.get_teams():
            first_line = first_line + str(t.id).rjust(3) + " "
        print(first_line)

        last_day = self.get_last_day()
        for d in self.schedule:
            if d.number > last_day:
                break

            day_string = " "
            if d.day_code >= 0:
                day_string = d.get_day_letter()
            type_string = " "
            if len(d.games_today) > 0:
                type_string = str(d.games_today[0].type)[0]
            number_string = day_string + str(d.number) + type_string
            line = number_string.rjust(start_padding) + " "

            for t in self.scheduler.league.get_teams():
                g = d.get_team_game_today(t)
                line_component = ""
                if g is not None:
                    o = g.get_other_team(t)
                    if o is not None:
                        home_away_code = "H" if g.home is t else "A"
                        line_component = (str(o.id) + home_away_code).rjust(3) + " "
                if line_component == "":
                    line_component = "    "
                line = line + line_component
            print(line)
