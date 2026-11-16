import math
import random
import re
from collections import defaultdict
from decimal import Decimal

import groovy_math
import math_util
import scheduler_settings as ss
from elements.day import Day, SUNDAY
from elements.day_type import DayType
from elements.game import Game
from elements.schedule import Schedule
from elements.series import Series
from elements.series_type import SeriesType
from math_util import jdiv, jmod
from structure.division import Division
from structure.double_round_robin_group import DoubleRoundRobinGroup
from structure.grouped_opponents_round_robin_group import GroupedOpponentsRoundRobinGroup
from structure.league import League
from structure.opponent_pool import OpponentPool
from structure.round_robin_group import RoundRobinGroup
from structure.subleague import Subleague
from structure.team import Team

OVERSCHEDULE_FACTOR = Decimal("1.2")
LEFTOVER_SPREAD_POINT = Decimal("0.3")


# -------------------------------------------------------------------------
# Arithmetic on preferred series lengths, matching Groovy's number rules:
# int operands use exact integer math, float operands use float math,
# and the result is truncated toward zero when stored in an int.
# -------------------------------------------------------------------------

def _div_int(a, b):
    return int(a / b) if isinstance(b, float) else jdiv(a, b)


def _mod_int(a, b):
    return int(math.fmod(a, b)) if isinstance(b, float) else jmod(a, b)


def _mul_int(a, b):
    if isinstance(b, float):
        return int(float(a) * b)
    return int(a * Decimal(int(b)))


def _groovy_iterable(value):
    """Groovy's for-in over an arbitrary value: lists as-is, strings by character, others as one item."""
    if value is None:
        return []
    if isinstance(value, (list, str)):
        return list(value)
    return [value]


class Scheduler:
    DEBUG = False
    break_days = 15
    breaks_split_series = False
    fine_schedule_adjustment = False

    INDEX_DIVISIONAL = 0
    INDEX_SUBLEAGUE = 1
    INDEX_INTERLEAGUE = 2

    # Preferred series length per category. Settings arrive as floats (see
    # scheduler_settings._typed_return), so entries may be int or float, exactly as
    # in the original. Use the _*_int helpers above for arithmetic on them.
    preferred_series_lengths = [3, 3, 3]

    def __init__(self):
        self.total_games = 0
        self.longest_possible_series = 1000
        self.start_day_of_week = -1
        self.off_days_of_week = []
        self.non_off_days_of_week = []
        self.allstar_break_days = 3
        self.allstar_percentage = 50
        self.allstar_day_of_week = -1
        self.match_subleague_pools = False
        self.match_interleague_pools_by_division = False
        self.match_interleague_pools_by_subleague = False
        self.games_against_division = 50
        self.divisional_pool_count = 1
        self.games_against_subleague = 30
        self.subleague_pool_count = 2
        self.games_against_interleague = 20
        self.interleague_pool_count = 2
        self.required_games = [self.games_against_division, self.games_against_subleague, self.games_against_interleague]
        self._compute_series_counts()
        self.interleague_cycle_time = Decimal(1)
        self.subleague_cycle_time = Decimal(1)
        self.divisional_cycle_time = Decimal(1)
        self.divisional_byes = Decimal(0)
        self.subleague_byes = Decimal(0)
        self.interleague_byes = Decimal(0)
        self.divisional_bye_days = 0
        self.subleague_bye_days = 0
        self.interleague_bye_days = 0
        self.priorities = [Scheduler.INDEX_DIVISIONAL, Scheduler.INDEX_SUBLEAGUE, Scheduler.INDEX_INTERLEAGUE]
        self.first_start_time = 1100
        self.last_start_time = 2100
        self.start_offset = 5
        self.simultaneous_games = 2
        self.interleague_play = True
        self.balanced_schedule = False
        self.league = None
        self.largest_preferred_series_length = 0
        self.shortest_preferred_series_length = 1000
        self.use_output_date = True

    @staticmethod
    def _pref(i):
        return Scheduler.preferred_series_lengths[i]

    def _compute_series_counts(self):
        pref = Scheduler._pref
        self.divisional_series = _div_int(self.games_against_division, pref(Scheduler.INDEX_DIVISIONAL))
        self.subleague_series = _div_int(self.games_against_subleague, pref(Scheduler.INDEX_SUBLEAGUE))
        self.interleague_series = _div_int(self.games_against_interleague, pref(Scheduler.INDEX_INTERLEAGUE))
        self.divisional_leftover = _mod_int(self.games_against_division, pref(Scheduler.INDEX_DIVISIONAL))
        self.spread_divisional_leftover = (pref(Scheduler.INDEX_DIVISIONAL) <= self.longest_possible_series - 1
                                           and self.divisional_leftover < 2)
        self.subleague_leftover = _mod_int(self.games_against_subleague, pref(Scheduler.INDEX_SUBLEAGUE))
        self.spread_subleague_leftover = (pref(Scheduler.INDEX_SUBLEAGUE) <= self.longest_possible_series - 1
                                          and self.subleague_leftover < 2)
        self.interleague_leftover = _mod_int(self.games_against_interleague, pref(Scheduler.INDEX_INTERLEAGUE))
        self.spread_interleague_leftover = (pref(Scheduler.INDEX_INTERLEAGUE) <= self.longest_possible_series - 1
                                            and self.interleague_leftover < 2)

    # ---------------------------------------------------------------------
    # Settings and league structure
    # ---------------------------------------------------------------------

    def load_settings(self, settings):
        self.interleague_play = ss.as_boolean(ss.optional(settings, "general", "interleague", True))
        self.balanced_schedule = ss.as_boolean(ss.optional(settings, "general", "balanced", False))
        self.league = self.generate_league_structure(str(ss.required(settings, "general", "structure")))
        self.use_output_date = ss.as_boolean(ss.optional(settings, "general", "output-file-date", True))

        lengths = Scheduler.preferred_series_lengths
        lengths[Scheduler.INDEX_DIVISIONAL] = ss.required(settings, "divisional-series", "preferred_length")
        self.divisional_pool_count = ss.as_int(ss.required(settings, "divisional-series", "pool_count"))
        lengths[Scheduler.INDEX_SUBLEAGUE] = ss.required(settings, "subleague-series", "preferred_length")
        self.subleague_pool_count = ss.as_int(ss.required(settings, "subleague-series", "pool_count"))
        lengths[Scheduler.INDEX_INTERLEAGUE] = ss.required(settings, "interleague-series", "preferred_length")
        self.interleague_pool_count = ss.as_int(ss.required(settings, "interleague-series", "pool_count"))

        Scheduler.break_days = ss.as_int(ss.required(settings, "break", "break_days"))
        self.allstar_percentage = ss.as_int(ss.optional(settings, "break", "all_star_percentage", -1))
        self.allstar_break_days = ss.as_int(ss.optional(settings, "break", "all_star_length", 3))
        temp = ss.optional(settings, "break", "all_star_day_of_week", "none")
        if temp != "none":
            self.allstar_day_of_week = Day.string_to_day_code(str(temp))
        self.start_day_of_week = Day.string_to_day_code(str(ss.optional(settings, "break", "start_day_of_week", "none")))
        for day in _groovy_iterable(ss.optional(settings, "break", "off_days_of_week", [])):
            self.off_days_of_week.append(Day.string_to_day_code(str(day)))
        for day in _groovy_iterable(ss.optional(settings, "break", "non_off_days_of_week", [])):
            self.non_off_days_of_week.append(Day.string_to_day_code(str(day)))
        Scheduler.breaks_split_series = ss.as_boolean(ss.optional(settings, "break", "mid_series_breaks", False))

        self.games_against_division = ss.as_int(ss.required(settings, "schedule", "divisional_games"))
        self.required_games[Scheduler.INDEX_DIVISIONAL] = self.games_against_division
        self.games_against_subleague = ss.as_int(ss.required(settings, "schedule", "subleague_games"))
        self.required_games[Scheduler.INDEX_SUBLEAGUE] = self.games_against_subleague
        self.games_against_interleague = ss.as_int(ss.required(settings, "schedule", "interleague_games"))
        self.required_games[Scheduler.INDEX_INTERLEAGUE] = self.games_against_interleague

        self.match_subleague_pools = ss.as_boolean(ss.optional(settings, "schedule", "match_divisions", True))
        self.match_interleague_pools_by_division = ss.as_boolean(
            ss.optional(settings, "schedule", "match_subleagues_by_division", False))
        self.match_interleague_pools_by_subleague = ss.as_boolean(
            ss.optional(settings, "schedule", "match_subleagues", False))
        if self.match_interleague_pools_by_division and self.match_interleague_pools_by_subleague:
            self.match_interleague_pools_by_division = False
            print("Both match interleague pools by division and match interleague pools by subleague are enabled. "
                  "Disabling interleague pools by division.")

        self.total_games = self.games_against_division + self.games_against_subleague + self.games_against_interleague

        self.first_start_time = ss.as_int(ss.optional(settings, "time", "first_start", 1100))
        self.last_start_time = ss.as_int(ss.optional(settings, "time", "last_start", 2100))
        self.start_offset = ss.as_int(ss.optional(settings, "time", "start_offset", 5))
        self.simultaneous_games = ss.as_int(ss.optional(settings, "time", "simultaneous_games", 2))

        print("All-star game is " + ("enabled" if self.allstar_percentage > 0 else "disabled"))
        print("Schedule options: interleague " + ("yes" if self.interleague_play else "no")
              + " balanced " + ("yes" if self.balanced_schedule else "no"))

    def generate_league_structure(self, league_structure):
        """Parses e.g. "SL1_D1_T4_D2_T4" (underscores ignored) into a league of subleagues, divisions and teams."""
        league_structure = league_structure.replace("_", "")
        subleague_id = 1
        division_id = 1
        team_id = 1
        l = League()
        l.id = 1
        for sl_string in league_structure.split("SL"):
            if sl_string.strip() == "":
                continue
            sl = Subleague(l)
            sl.id = subleague_id
            subleague_id += 1
            sl_string = re.sub(r"\A[0-9]*", "", sl_string, count=1)
            for div_string in sl_string.split("D"):
                if div_string.strip() == "":
                    continue
                div = Division(sl)
                div.id = division_id
                division_id += 1
                team_count = int(re.sub("T", "", re.sub(r"\A[0-9]*", "", div_string, count=1), count=1))
                for _ in range(team_count):
                    t = Team(div)
                    t.id = team_id
                    team_id += 1
        return l

    # ---------------------------------------------------------------------
    # Opponent pools
    # ---------------------------------------------------------------------

    def _do_pool_size_checks(self):
        league = self.league
        if self.match_subleague_pools:
            for sl in league.subleagues:
                division_size_counts = defaultdict(int)
                for d in sl.divisions:
                    division_size_counts[len(d.teams)] += 1
                for team_count in division_size_counts.values():
                    if team_count % 2 != 0:
                        if self.match_subleague_pools:
                            print("Unable to match subleague pools. Falling back to random subleague pools.")
                        self.match_subleague_pools = False

        if self.match_interleague_pools_by_division:
            divisions_to_match = list(league.get_divisions())
            matched_divisions = []
            random.shuffle(divisions_to_match)
            for d in league.get_divisions():
                if not self.match_interleague_pools_by_division:
                    break
                if d in matched_divisions:
                    continue
                for opponent in league.get_interleague_divisions_for(d):
                    if len(divisions_to_match) == 0:
                        print("Unable to match interleague pools by division. Falling back to random interleague pools.")
                        self.match_interleague_pools_by_division = False
                        break
                    if len(opponent.teams) == len(d.teams):
                        matched_divisions.append(d)
                        matched_divisions.append(opponent)
                        _remove(divisions_to_match, opponent)
                        _remove(divisions_to_match, d)
                        break
        elif self.match_interleague_pools_by_subleague:
            subleague_size_counts = defaultdict(int)
            for sl in league.subleagues:
                subleague_size_counts[len(sl.get_teams())] += 1
            for team_count in subleague_size_counts.values():
                if team_count % 2 != 0:
                    if self.match_interleague_pools_by_subleague:
                        print("Unable to match interleague pools by subleague. Falling back to random interleague pools.")
                    self.match_interleague_pools_by_subleague = False

    def generate_opponent_pools(self):
        self._do_pool_size_checks()

        for d in self.league.get_divisions():
            divisional_teams = list(d.get_teams())
            teams_per_pool = len(divisional_teams) // self.divisional_pool_count
            leftover_teams = len(divisional_teams) % self.divisional_pool_count

            for _ in range(self.divisional_pool_count):
                pool_teams = []
                for _ in range(teams_per_pool):
                    picked = divisional_teams[random.randrange(len(divisional_teams))]
                    pool_teams.append(picked)
                    divisional_teams.remove(picked)
                if leftover_teams > 0:
                    leftover_teams -= 1
                    picked = divisional_teams[random.randrange(len(divisional_teams))]
                    pool_teams.append(picked)
                    divisional_teams.remove(picked)

                divisional_pool = OpponentPool()
                divisional_pool.type = SeriesType.DIVISIONAL
                divisional_pool.teams = pool_teams
                self.league.divisional_pools.append(divisional_pool)

        for pool in self.league.divisional_pools:
            print("Divisional pool: " + str(pool.teams))

        if self.match_subleague_pools:
            self._generate_matched_subleague_pools()
        else:
            self._generate_random_subleague_pools()

        if not self.interleague_play or self.games_against_interleague == 0:
            return

        if self.match_interleague_pools_by_division:
            self._generate_matched_interleague_pools_by_division()
        elif self.match_interleague_pools_by_subleague:
            self._generate_matched_interleague_pools_by_subleague()
        else:
            self._generate_random_interleague_pools()

    @staticmethod
    def _contribute_teams(pools, teams, pool_count, stop_when_none):
        """Spreads teams randomly and evenly over pools; extras go to the smallest pool."""
        teams_contributed = []
        teams_to_contribute = len(teams) // pool_count
        extra_teams = len(teams) % pool_count

        for pool in pools:
            uncontributed_teams = [t for t in teams if t not in teams_contributed]
            random.shuffle(uncontributed_teams)
            if stop_when_none and teams_to_contribute - 1 < 0:
                break
            contributions = uncontributed_teams[:teams_to_contribute]
            pool.teams.extend(contributions)
            teams_contributed.extend(contributions)

        for _ in range(extra_teams):
            smallest = Scheduler._smallest_pool(pools)
            first = [t for t in teams if t not in teams_contributed][0]
            smallest.teams.append(first)
            teams_contributed.append(first)

    def _generate_random_subleague_pools(self):
        if Scheduler.DEBUG:
            print("Generating random subleague pools")

        for sl in self.league.get_subleagues():
            if self.required_games[Scheduler.INDEX_SUBLEAGUE] == 0:
                break

            subleague_pools = []
            for _ in range(self.subleague_pool_count):
                p = OpponentPool()
                p.type = SeriesType.SUBLEAGUE
                subleague_pools.append(p)

            for d in sl.divisions:
                Scheduler._contribute_teams(subleague_pools, d.get_teams(), self.subleague_pool_count, True)

            for pool in subleague_pools:
                print("Subleague pool: " + str(pool.teams))
            self.league.subleague_pools.extend(subleague_pools)

    @staticmethod
    def _smallest_pool(pools):
        smallest_pool = None
        smallest_size = 1000
        for pool in pools:
            if smallest_pool is None:
                smallest_size = len(pool.teams)
                smallest_pool = pool
            if len(pool.teams) < smallest_size:
                smallest_size = len(pool.teams)
                smallest_pool = pool
        return smallest_pool

    def _generate_matched_subleague_pools(self):
        if Scheduler.DEBUG:
            print("Generating matched subleague pools")

        subleague_pools = []
        for sl in self.league.subleagues:
            divisions_by_size = defaultdict(list)
            for d in sl.divisions:
                divisions_by_size[len(d.teams)].append(d)
            for divisions in divisions_by_size.values():
                if len(divisions) % 2 != 0:
                    continue
                random.shuffle(divisions)
                for i in range(0, len(divisions), 2):
                    p = OpponentPool()
                    p.type = SeriesType.SUBLEAGUE
                    p.teams.extend(divisions[i].teams)
                    p.teams.extend(divisions[i + 1].teams)
                    subleague_pools.append(p)

        for pool in subleague_pools:
            print("Subleague pool: " + str(pool.teams))
        self.league.subleague_pools = subleague_pools

    def _generate_random_interleague_pools(self):
        interleague_pools = []
        for _ in range(self.interleague_pool_count):
            p = OpponentPool()
            p.type = SeriesType.INTERLEAGUE
            interleague_pools.append(p)

        for sl in self.league.subleagues:
            # With zero teams to contribute (more pools than teams), the original Groovy's
            # list[0..-1] put the whole subleague in this pool; this contributes none.
            Scheduler._contribute_teams(interleague_pools, sl.get_teams(), self.interleague_pool_count, False)

        for pool in interleague_pools:
            print("Interleague pool: " + str(pool.teams))
        self.league.interleague_pools = interleague_pools

    def _generate_matched_interleague_pools_by_division(self):
        divisions_to_match = list(self.league.get_divisions())
        matched_divisions = []
        interleague_pools = []
        for d in self.league.get_divisions():
            if not self.match_interleague_pools_by_division:
                break
            if d in matched_divisions:
                continue

            valid_interleague_divisions = [v for v in self.league.get_interleague_divisions_for(d)
                                           if v not in matched_divisions]
            random.shuffle(valid_interleague_divisions)
            for opponent in valid_interleague_divisions:
                if len(divisions_to_match) == 0:
                    break
                if len(opponent.teams) == len(d.teams):
                    _remove(divisions_to_match, opponent)
                    _remove(divisions_to_match, d)
                    matched_divisions.append(opponent)
                    matched_divisions.append(d)
                    p = OpponentPool()
                    p.type = SeriesType.INTERLEAGUE
                    p.teams.extend(d.teams)
                    p.teams.extend(opponent.teams)
                    interleague_pools.append(p)
                    break

        for pool in interleague_pools:
            print("Interleague pool: " + str(pool.teams))
        self.league.interleague_pools = interleague_pools

    def _generate_matched_interleague_pools_by_subleague(self):
        interleague_pools = []
        subleagues_by_size = defaultdict(list)
        for sl in self.league.get_subleagues():
            subleagues_by_size[len(sl.get_teams())].append(sl)

        for subleagues in subleagues_by_size.values():
            if len(subleagues) % 2 != 0:
                continue
            random.shuffle(subleagues)
            for i in range(0, len(subleagues), 2):
                p = OpponentPool()
                # The original labels these pools SUBLEAGUE even though they hold interleague matchups.
                p.type = SeriesType.SUBLEAGUE
                p.teams.extend(subleagues[i].get_teams())
                p.teams.extend(subleagues[i + 1].get_teams())
                interleague_pools.append(p)

        for pool in interleague_pools:
            print("Interleague pool: " + str(pool.teams))
        self.league.interleague_pools = interleague_pools

    # ---------------------------------------------------------------------
    # Size checks
    # ---------------------------------------------------------------------

    @staticmethod
    def _fewest_acceptable_series(cycle_time):
        for i in range(1, 1000):
            result = math_util.close_round(cycle_time * i)
            print(result)
            if math_util.is_whole_number(result):
                return i
        return -1

    @staticmethod
    def _max_cycle_time(current, pools):
        for p in pools:
            if p.size() % 2 == 1:
                current = max(current, groovy_math.div(p.size(), p.size() - 1))
        return current

    def _print_currently(self, index, series):
        print("Currently: " + str(self.required_games[index]) + " games / " + str(Scheduler._pref(index))
              + " games per series = " + str(series))

    def _do_schedule_size_checks(self):
        pref = Scheduler._pref
        self._compute_series_counts()

        print("Divisional series: " + str(self.divisional_series) + " of " + str(pref(Scheduler.INDEX_DIVISIONAL))
              + " plus " + str(self.divisional_leftover))
        print("Subleague series: " + str(self.subleague_series) + " of " + str(pref(Scheduler.INDEX_SUBLEAGUE))
              + " plus " + str(self.subleague_leftover))
        print("Interleague series: " + str(self.interleague_series) + " of " + str(pref(Scheduler.INDEX_INTERLEAGUE))
              + " plus " + str(self.interleague_leftover))

        self.interleague_cycle_time = Scheduler._max_cycle_time(Decimal(1), self.league.interleague_pools)
        self.subleague_cycle_time = Scheduler._max_cycle_time(Decimal(1), self.league.subleague_pools)
        self.divisional_cycle_time = Scheduler._max_cycle_time(Decimal(1), self.league.divisional_pools)
        print("Cycle times I/S/D: " + str(self.interleague_cycle_time) + " " + str(self.subleague_cycle_time)
              + " " + str(self.divisional_cycle_time))

        odd_pool_message = " games. For schedules with pools containing an odd number of teams, the number of series must be even."
        if self.divisional_series % 2 != 0 and self.divisional_cycle_time > 1:
            print("Unable to fit divisional" + odd_pool_message)
            self._print_currently(Scheduler.INDEX_DIVISIONAL, self.divisional_series)
            return False
        if self.subleague_series % 2 != 0 and self.subleague_cycle_time > 1:
            print("Unable to fit subleague" + odd_pool_message)
            self._print_currently(Scheduler.INDEX_SUBLEAGUE, self.subleague_series)
            return False
        if self.interleague_series % 2 != 0 and self.interleague_cycle_time > 1:
            print("Unable to fit interleague" + odd_pool_message)
            self._print_currently(Scheduler.INDEX_INTERLEAGUE, self.interleague_series)
            return False

        if self.divisional_cycle_time == 1 and self.subleague_cycle_time == 1 and self.interleague_cycle_time == 1:
            return True

        self.divisional_byes = math_util.close_round(_byes(self.divisional_series, self.divisional_cycle_time))
        if not math_util.is_whole_number(self.divisional_byes):
            min_series = Scheduler._fewest_acceptable_series(self.divisional_cycle_time)
            print("Divisional games must be organized into a multiple of " + str(min_series) + " series.")
            self._print_currently(Scheduler.INDEX_DIVISIONAL, self.divisional_series)
            return False

        self.subleague_byes = math_util.close_round(_byes(self.subleague_series, self.subleague_cycle_time))
        if not math_util.is_whole_number(self.subleague_byes):
            min_series = Scheduler._fewest_acceptable_series(self.subleague_cycle_time)
            print("Subleague games must be organized into a multiple of " + str(min_series) + " series.")
            self._print_currently(Scheduler.INDEX_SUBLEAGUE, self.subleague_series)
            return False

        self.interleague_byes = math_util.close_round(_byes(self.interleague_series, self.interleague_cycle_time))
        print("Rounded byes: " + str(self.interleague_byes))
        print("Normal byes: " + str(_byes(self.interleague_series, self.interleague_cycle_time)))
        if not math_util.is_whole_number(self.interleague_byes):
            min_series = Scheduler._fewest_acceptable_series(self.interleague_cycle_time)
            print("Interleague games must be organized into a multiple of " + str(min_series) + " series.")
            self._print_currently(Scheduler.INDEX_INTERLEAGUE, self.interleague_series)
            return False

        self.divisional_bye_days = _mul_int(self.divisional_byes, pref(Scheduler.INDEX_DIVISIONAL))
        self.subleague_bye_days = _mul_int(self.subleague_byes, pref(Scheduler.INDEX_SUBLEAGUE))
        self.interleague_bye_days = _mul_int(self.interleague_byes, pref(Scheduler.INDEX_INTERLEAGUE))
        print("Byes/Bye Days I/S/D: " + str(self.interleague_byes) + "/" + str(self.interleague_bye_days)
              + " " + str(self.subleague_byes) + "/" + str(self.subleague_bye_days)
              + " " + str(self.divisional_byes) + "/" + str(self.divisional_bye_days))
        return True

    # ---------------------------------------------------------------------
    # Schedule structure
    # ---------------------------------------------------------------------

    def _is_break_candidate(self, candidate_day):
        return (candidate_day.type != DayType.BREAK and candidate_day.type != DayType.ALLSTAR
                and candidate_day.day_code not in self.non_off_days_of_week)

    def _generate_schedule_structure(self):
        pref = Scheduler._pref
        total_length = self._get_desired_schedule_length()
        print("Length of schedule: at most " + str(total_length) + " days")
        calendar = Schedule()
        calendar.initialize(self, total_length, False)
        days = calendar.schedule

        breaks_placed = 0
        break_days = Scheduler.break_days
        if break_days > 0:
            days_between_breaks = jdiv(total_length, break_days)
            remainder_days = jmod(total_length, break_days)
            if Scheduler.DEBUG:
                print("Days between breaks: " + str(days_between_breaks) + " Remainder days: " + str(remainder_days))

            i = days_between_breaks - 1
            while i < len(days):
                candidate_day = days[i]
                if self._is_break_candidate(candidate_day):
                    breaks_placed += 1
                    candidate_day.type = DayType.BREAK
                else:
                    candidate_offset = 1
                    while True:
                        if i + candidate_offset < len(days):
                            candidate_day = days[i + candidate_offset]
                            if self._is_break_candidate(candidate_day):
                                candidate_day.type = DayType.BREAK
                                breaks_placed += 1
                                break
                        if i - candidate_offset >= 0:
                            candidate_day = days[i - candidate_offset]
                            if self._is_break_candidate(candidate_day):
                                candidate_day.type = DayType.BREAK
                                breaks_placed += 1
                                break
                        if i - candidate_offset < 0 and i + candidate_offset >= len(days):
                            break
                        candidate_offset += 1

                if remainder_days > 0:
                    remainder_days -= 1
                    i += 1
                if breaks_placed >= break_days:
                    break
                i += days_between_breaks
        print("Placed " + str(breaks_placed) + " of " + str(break_days) + " break days")

        remaining_divisional_games = self.games_against_division + self.divisional_bye_days
        remaining_subleague_games = self.games_against_subleague + self.subleague_bye_days
        remaining_interleague_games = self.games_against_interleague + self.interleague_bye_days
        remaining_divisional_series = int(Decimal(self.divisional_series) + self.divisional_byes)
        remaining_subleague_series = int(Decimal(self.subleague_series) + self.subleague_byes)
        remaining_interleague_series = int(Decimal(self.interleague_series) + self.interleague_byes)
        scheduling = False
        currently_scheduling = None
        current_series = None
        current_run_length = 0
        scheduled_in_current_run = 0
        day_index = 0
        leftover_spread_day = Decimal(len(days)) * LEFTOVER_SPREAD_POINT
        overschedule_factor = float(OVERSCHEDULE_FACTOR)

        while remaining_divisional_games + remaining_subleague_games + remaining_interleague_games > 0:
            if not scheduling:
                percent_divisional = 0.0
                if self.games_against_division > 0:
                    percent_divisional = remaining_divisional_games / (self.games_against_division + self.divisional_bye_days)
                percent_subleague = 0.0
                if self.games_against_subleague > 0:
                    percent_subleague = remaining_subleague_games / (self.games_against_subleague + self.subleague_bye_days)
                percent_interleague = 0.0
                if self.games_against_interleague > 0:
                    percent_interleague = (remaining_interleague_games
                                           / (self.games_against_interleague + self.interleague_bye_days))

                if days[day_index].type == DayType.BREAK:
                    if Scheduler.DEBUG:
                        print("Break day: " + str(day_index))
                    day_index += 1
                else:
                    current_series = Series()
                    after_allstar = day_index >= calendar.last_allstar_break_day_index
                    days_to_allstar = calendar.first_allstar_break_day_index - day_index
                    is_divisional_candidate = False
                    is_subleague_candidate = False
                    is_interleague_candidate = False
                    current_run = calendar.get_run_starting_on(day_index)
                    if Scheduler.DEBUG:
                        print("Current run without break days: " + str(current_run))

                    if not (percent_divisional <= 0) and current_run == pref(Scheduler.INDEX_DIVISIONAL):
                        if Scheduler.DEBUG:
                            print("Divisional is perfect match: adding as candidate")
                        is_divisional_candidate = True
                    if not (percent_subleague <= 0) and current_run == pref(Scheduler.INDEX_SUBLEAGUE):
                        if Scheduler.DEBUG:
                            print("Subleague is perfect match: adding as candidate")
                        is_subleague_candidate = True
                    if not (percent_interleague <= 0) and current_run == pref(Scheduler.INDEX_INTERLEAGUE):
                        if Scheduler.DEBUG:
                            print("Interleague is perfect match: adding as candidate")
                        is_interleague_candidate = True

                    if (percent_divisional * overschedule_factor <= percent_subleague
                            and percent_divisional * overschedule_factor <= percent_interleague):
                        if Scheduler.DEBUG:
                            print("Correcting divisional overscheduling")
                        is_divisional_candidate = False
                    if (percent_subleague * overschedule_factor <= percent_divisional
                            and percent_subleague * overschedule_factor <= percent_interleague):
                        if Scheduler.DEBUG:
                            print("Correcting subleague overscheduling")
                        is_subleague_candidate = False
                    if (percent_interleague * overschedule_factor <= percent_divisional
                            and percent_interleague * overschedule_factor <= percent_subleague):
                        if Scheduler.DEBUG:
                            print("Correcting interleague overscheduling")
                        is_interleague_candidate = False

                    if not is_divisional_candidate and not is_subleague_candidate and not is_interleague_candidate:
                        if Scheduler.DEBUG:
                            print("No perfect matches: adding all as candidates")
                        is_divisional_candidate = True
                        is_subleague_candidate = True
                        is_interleague_candidate = True

                    split = Scheduler.breaks_split_series or after_allstar
                    if (is_divisional_candidate and not (percent_divisional <= 0)
                            and (not is_subleague_candidate or not (percent_divisional < percent_subleague))
                            and (not is_interleague_candidate or not (percent_divisional < percent_interleague))
                            and (split or days_to_allstar > pref(Scheduler.INDEX_DIVISIONAL))):
                        currently_scheduling = DayType.DIVISIONAL
                        current_series.type = SeriesType.DIVISIONAL
                    elif (is_subleague_candidate and not (percent_subleague <= 0)
                          and (not is_divisional_candidate or not (percent_subleague < percent_divisional))
                          and (not is_interleague_candidate or not (percent_subleague < percent_interleague))
                          and (split or days_to_allstar > pref(Scheduler.INDEX_SUBLEAGUE))):
                        currently_scheduling = DayType.SUBLEAGUE
                        current_series.type = SeriesType.SUBLEAGUE
                    elif (is_interleague_candidate and not (percent_interleague <= 0)
                          and (split or days_to_allstar > pref(Scheduler.INDEX_INTERLEAGUE))):
                        currently_scheduling = DayType.INTERLEAGUE
                        current_series.type = SeriesType.INTERLEAGUE

                    if currently_scheduling is None:
                        if Scheduler.DEBUG:
                            print("Scheduling no series starting on day " + str(day_index))
                        day_index += 1
                    else:
                        if Scheduler.DEBUG:
                            print("Scheduling " + str(currently_scheduling) + " starting on day " + str(day_index))
                        today = days[day_index]
                        today.series_starting_today.append(current_series)
                        today.series_ongoing_today.append(current_series)
                        current_series.start_day = day_index + 1
                        scheduling = True
            elif days[day_index].type == DayType.BREAK or days[day_index].type == DayType.ALLSTAR:
                if scheduling and current_series is not None:
                    today = days[day_index]
                    print("Series type " + str(current_series.type) + " impinges on break day "
                          + today.get_day_letter() + str(day_index + 1) + "!")
                    today.series_ongoing_today.append(current_series)
                day_index += 1
            else:
                if current_run_length == 0:
                    if currently_scheduling == DayType.DIVISIONAL:
                        if remaining_divisional_series <= 0:
                            if self.divisional_leftover > 0:
                                current_run_length = self.divisional_leftover
                                self.divisional_leftover = 0
                        else:
                            remaining_divisional_series -= 1
                            current_run_length = int(pref(Scheduler.INDEX_DIVISIONAL))
                            if (self.spread_divisional_leftover and self.divisional_leftover > 0
                                    and day_index > leftover_spread_day):
                                current_run_length += 1
                                self.divisional_leftover -= 1
                    elif currently_scheduling == DayType.SUBLEAGUE:
                        if remaining_subleague_series <= 0:
                            if self.subleague_leftover > 0:
                                current_run_length = self.subleague_leftover
                                self.subleague_leftover = 0
                        else:
                            remaining_subleague_series -= 1
                            current_run_length = int(pref(Scheduler.INDEX_SUBLEAGUE))
                            if (self.spread_subleague_leftover and self.subleague_leftover > 0
                                    and day_index > leftover_spread_day):
                                current_run_length += 1
                                self.subleague_leftover -= 1
                    elif currently_scheduling == DayType.INTERLEAGUE:
                        if remaining_interleague_series <= 0:
                            if self.interleague_leftover > 0:
                                current_run_length = self.interleague_leftover
                                self.interleague_leftover = 0
                        else:
                            remaining_interleague_series -= 1
                            current_run_length = int(pref(Scheduler.INDEX_INTERLEAGUE))
                            if (self.spread_interleague_leftover and self.interleague_leftover > 0
                                    and day_index > leftover_spread_day):
                                current_run_length += 1
                                self.interleague_leftover -= 1
                    current_series.length = current_run_length

                today = days[day_index]
                today.type = currently_scheduling
                scheduled_in_current_run += 1
                g = Game()
                g.parent = current_series
                g.day = today
                g.type = SeriesType.get_series_type_for_day_type(currently_scheduling)
                current_series.games.append(g)
                today.series_ongoing_today.append(current_series)
                today.games_today.append(g)
                if currently_scheduling == DayType.DIVISIONAL:
                    remaining_divisional_games -= 1
                elif currently_scheduling == DayType.SUBLEAGUE:
                    remaining_subleague_games -= 1
                elif currently_scheduling == DayType.INTERLEAGUE:
                    remaining_interleague_games -= 1

                if scheduled_in_current_run >= current_run_length:
                    current_series.end_day = day_index + 1
                    current_run_length = 0
                    scheduled_in_current_run = 0
                    scheduling = False
                    currently_scheduling = None
                    current_series = None
                day_index += 1

        counts = {t: [0, 0] for t in (SeriesType.DIVISIONAL, SeriesType.SUBLEAGUE, SeriesType.INTERLEAGUE)}
        for d in calendar.schedule:
            for s in d.series_starting_today:
                if s.type in counts:
                    counts[s.type][0] += len(s.games)
                    counts[s.type][1] += 1
        i_days, i_count = counts[SeriesType.INTERLEAGUE]
        s_days, s_count = counts[SeriesType.SUBLEAGUE]
        d_days, d_count = counts[SeriesType.DIVISIONAL]
        print("Scheduled games/series I/S/D: " + str(i_days) + "/" + str(i_count) + " " + str(s_days) + "/"
              + str(s_count) + " " + str(d_days) + "/" + str(d_count))

        if not Scheduler.breaks_split_series:
            calendar.move_breaks_to_end_of_series()
        return calendar

    def get_team_by_id(self, team_id):
        for t in self.league.get_teams():
            if t.id == team_id:
                return t
        return None

    # ---------------------------------------------------------------------
    # Matchups
    # ---------------------------------------------------------------------

    def generate_matchups(self, calendar):
        schedule = Schedule()
        schedule.initialize(self, len(calendar.schedule), False)
        interleague_groups = []
        subleague_groups = []
        divisional_groups = []

        for p in self.league.interleague_pools:
            double_round_robin_group = DoubleRoundRobinGroup.create_with(
                RoundRobinGroup.Type.INTERLEAGUE, p, self.interleague_cycle_time)
            if double_round_robin_group is not None:
                if Scheduler.DEBUG:
                    print("Using double round robin interleague group")
                interleague_groups.append(double_round_robin_group)
            else:
                interleague_groups.append(GroupedOpponentsRoundRobinGroup(
                    RoundRobinGroup.Type.INTERLEAGUE, p, self.interleague_cycle_time,
                    self.match_interleague_pools_by_division))

        for p in self.league.subleague_pools:
            # As in the original, the double round robin attempt uses the interleague cycle time.
            double_round_robin_group = DoubleRoundRobinGroup.create_with(
                RoundRobinGroup.Type.SUBLEAGUE, p, self.interleague_cycle_time)
            if double_round_robin_group is not None:
                if Scheduler.DEBUG:
                    print("Using double round robin subleague group")
                subleague_groups.append(double_round_robin_group)
            else:
                subleague_groups.append(GroupedOpponentsRoundRobinGroup(
                    RoundRobinGroup.Type.SUBLEAGUE, p, self.subleague_cycle_time, self.match_subleague_pools))

        for p in self.league.divisional_pools:
            divisional_groups.append(RoundRobinGroup(p, self.divisional_cycle_time))

        for d in calendar.schedule:
            for calendar_series in d.series_starting_today:
                if calendar_series.type == SeriesType.INTERLEAGUE:
                    groups = interleague_groups
                elif calendar_series.type == SeriesType.SUBLEAGUE:
                    groups = subleague_groups
                else:
                    groups = divisional_groups

                for group in groups:
                    should_rotate = group.copy_series(schedule, calendar_series)
                    if should_rotate:
                        group.rotate()
        return schedule

    def _get_desired_schedule_length(self):
        desired_schedule_length = (self.total_games + Scheduler.break_days + self.divisional_bye_days
                                   + self.subleague_bye_days + self.interleague_bye_days)
        if self.allstar_percentage > 0:
            desired_schedule_length += self.allstar_break_days * 2 + self.largest_preferred_series_length

        if self.start_day_of_week != -1:
            if Scheduler.DEBUG:
                print("Week-aware mode: starting with " + str(desired_schedule_length) + " days...")
            available_days_per_week = 7 - len(self.off_days_of_week)
            weeks_required = 0
            days_available = 0
            while days_available < desired_schedule_length:
                weeks_required += 1
                days_available += available_days_per_week
            desired_schedule_length = weeks_required * 7
            if Scheduler.DEBUG:
                print("Week-aware mode: final length is " + str(desired_schedule_length) + " days")
        elif Scheduler.DEBUG:
            print("Non-week-aware mode: " + str(desired_schedule_length) + " days")
        return desired_schedule_length

    def schedule(self):
        # This local deliberately differs from the attribute, as in the original: it only caps
        # the preferred series lengths below.
        longest_possible_series = 1000
        if self.start_day_of_week != -1 and len(self.off_days_of_week) > 0:
            run = 0
            longest_run = 0
            first_off_day = self.off_days_of_week[0]
            for i in range(first_off_day, SUNDAY + first_off_day + 1):
                if i % 7 in self.off_days_of_week:
                    if run > longest_run:
                        longest_run = run
                    run = 0
                else:
                    run += 1
            if run > longest_run:
                longest_run = run
            longest_possible_series = longest_run
        print("Longest possible series: " + str(longest_possible_series))

        lengths = Scheduler.preferred_series_lengths
        self.largest_preferred_series_length = 0
        self.shortest_preferred_series_length = 1000
        for i in range(len(self.priorities)):
            if lengths[i] > longest_possible_series:
                lengths[i] = longest_possible_series
            if lengths[i] > self.largest_preferred_series_length:
                self.largest_preferred_series_length = int(lengths[i])
            if lengths[i] < self.shortest_preferred_series_length:
                self.shortest_preferred_series_length = int(lengths[i])

        print("Generating opponent pools...")
        self.generate_opponent_pools()

        result = self._do_schedule_size_checks()
        if not result:
            print("Aborting...")
            return Schedule()

        print("Generating schedule structure...")
        calendar = self._generate_schedule_structure()

        print("Generating games...")
        schedule = self.generate_matchups(calendar)
        schedule.success = True
        print("Schedule successfully generated. Tweaking...")
        print("Adjusting home-away balance...")
        schedule.home_away_balance()
        print("Intra-day scheduling...")
        schedule.schedule_intraday()
        return schedule


def _byes(series, cycle_time):
    """series * cycle_time - series, in exact decimal arithmetic."""
    return Decimal(series) * cycle_time - Decimal(series)


def _remove(items, item):
    """Java List.remove(Object): removes the first match if present."""
    if item in items:
        items.remove(item)
