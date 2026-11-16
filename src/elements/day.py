from elements.day_type import DayType

MONDAY = 0
TUESDAY = 1
WEDNESDAY = 2
THURSDAY = 3
FRIDAY = 4
SATURDAY = 5
SUNDAY = 6

_DAY_CODES = {"MONDAY": MONDAY, "TUESDAY": TUESDAY, "WEDNESDAY": WEDNESDAY, "THURSDAY": THURSDAY,
              "FRIDAY": FRIDAY, "SATURDAY": SATURDAY, "SUNDAY": SUNDAY}
_OOTP_DAY_CODES = {MONDAY: 2, TUESDAY: 3, WEDNESDAY: 4, THURSDAY: 5, FRIDAY: 6, SATURDAY: 7, SUNDAY: 1}
_DAY_LETTERS = {MONDAY: "M", TUESDAY: "T", WEDNESDAY: "W", THURSDAY: "R", FRIDAY: "F", SATURDAY: "S", SUNDAY: "S"}


class Day:
    def __init__(self):
        self.number = 0
        self.day_code = -1
        self.type = DayType.NORMAL
        self.series_starting_today = []
        self.series_ongoing_today = []
        self.games_today = []
        self.teams_playing_today = []

    @staticmethod
    def string_to_day_code(day):
        return _DAY_CODES.get(day.upper(), -1)

    @staticmethod
    def day_code_to_ootp_day_code(day):
        return _OOTP_DAY_CODES.get(day, -1)

    def get_day_letter(self):
        return _DAY_LETTERS.get(self.day_code, " ")

    def is_team_playing_today(self, t):
        return t in self.teams_playing_today

    def get_team_game_today(self, t):
        for g in self.games_today:
            if g.home is t or g.away is t:
                return g
        return None

    def get_index(self):
        return self.number - 1

    def __str__(self):
        return "D" + str(self.number)

    __repr__ = __str__
