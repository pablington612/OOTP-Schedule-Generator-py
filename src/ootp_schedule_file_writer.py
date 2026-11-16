import os
from datetime import datetime

from elements.day import Day
from elements.series_type import SeriesType


def write_schedule_file(settings, s):
    all_games = s.get_all_games()
    # Sort key copied from the original: the day number and start time joined as text, then parsed.
    all_games.sort(key=lambda g: int(str(g.day.number) + str(g.time)))

    prefix = ""
    prefix += "ILY_" if settings.interleague_play else "ILN_"
    prefix += "BGY_" if settings.balanced_schedule else "BGN_"
    prefix += "G" + str(settings.total_games) + "_"

    league = settings.league
    total_teams = "T" + str(len(league.get_teams()))
    if len(league.subleagues) == 1 and len(league.subleagues[0].divisions) == 1:
        structure = total_teams
    else:
        structure = ""
        for i, sl in enumerate(league.subleagues, start=1):
            structure += "SL" + str(i)
            for j, d in enumerate(sl.divisions, start=1):
                structure += "D" + str(j) + "T" + str(len(d.teams))

    timestamp = ""
    if settings.use_output_date:
        # The original's "YYYY" is a week-based year; the ISO week year is the closest match.
        # (strftime's %G is not supported on every platform.)
        now = datetime.now()
        timestamp = "%04d" % now.isocalendar()[0] + now.strftime("%m%d%H%M%S")
    suffix = "_C_autogen" + timestamp + ".lsdl"

    filename = prefix + structure + suffix
    # Many divisions overflow Windows' 255-char name / 260-char path limit; fall back to the team count.
    if len(os.path.abspath(filename)) > 259:
        filename = prefix + total_teams + suffix

    allstar_day = -1
    for g in all_games:
        if g.type == SeriesType.ALLSTAR:
            allstar_day = g.day.number
            break

    contents = ['<?xml version="1.0" encoding="ISO-8859-1"?>\n']
    contents.append('<SCHEDULE type="' + filename
                    + '" inter_league="' + ("1" if settings.interleague_play else "0")
                    + '" balanced_games="' + ("1" if settings.balanced_schedule else "0")
                    + '" games_per_team="' + str(settings.total_games)
                    + '" ')
    if allstar_day != -1:
        contents.append('allstar_game_day="' + str(allstar_day) + '" ')
    if settings.start_day_of_week != -1:
        contents.append('start_day_of_week="' + str(Day.day_code_to_ootp_day_code(settings.start_day_of_week)) + '" ')
    contents.append(">\n")
    contents.append("<GAMES>\n")

    most_recent_day = None
    for g in all_games:
        if g.day is not most_recent_day:
            contents.append("\n")
            most_recent_day = g.day
        game_type = "4" if g.type == SeriesType.ALLSTAR else "0"
        contents.append('<GAME day="' + str(g.day.number)
                        + '" time="' + str(g.time)
                        + '" away="' + str(g.away.id)
                        + '" home="' + str(g.home.id)
                        + '" type="' + game_type + '"/>\n')
    contents.append("</GAMES>\n")
    contents.append("</SCHEDULE>\n")

    with open(os.path.join(".", filename), "w", encoding="iso-8859-1", newline="\n") as output:
        output.write("".join(contents))
    print(filename)
