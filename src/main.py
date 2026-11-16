import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from console_util import read_line  # noqa: E402
from ini_loader import IniLoader, java_split  # noqa: E402
from ootp_schedule_file_writer import write_schedule_file  # noqa: E402
from scheduler import Scheduler  # noqa: E402

HELP = ("\n"
        "matchups             print matchups for all teams.\n"
        "matchups [t#|T#|#]   print matchups for the given team.\n"
        "days                 print the day-by-day schedule for all teams.\n"
        "team [t#|T#|#]       print the day-by-day schedule for the given team.\n"
        "grid                 print a schedule grid.\n"
        "write                write the schedule to a file and quit.\n"
        "regen                regenerate the schedule.\n"
        "quit                 quit.\n"
        "help                 this screen.                    \n")


def main(args):
    settings_file = "settings.ini"
    debug = False
    for arg in args:
        if arg.endswith(".ini"):
            settings_file = arg
        if arg == "--debug":
            debug = True

    settings = IniLoader(os.path.join(".", settings_file)).load()

    while True:
        s = Scheduler()
        s.load_settings(settings)
        line = read_line("Settings loaded. Proceed (y/n)? ")
        if line.lower() != "y":
            sys.exit(0)

        Scheduler.DEBUG = debug
        start_time = int(time.time() * 1000)
        sch = s.schedule()
        total_time = (int(time.time() * 1000) - start_time) / 1000.0
        print("Scheduled " + str(sch.total_series_scheduled) + " series (" + str(sch.total_games_scheduled)
              + " games) in " + str(total_time) + " seconds")
        rate = sch.total_series_scheduled / total_time if total_time else float("inf")
        print(str(rate) + " series/sec")

        if command_loop(s, sch):
            break

    write_schedule_file(s, sch)


def command_loop(s, sch):
    """Runs the interactive commands. True means write the schedule, False means regenerate."""
    while True:
        while not sch.success:
            line = read_line("Scheduling failed with " + str(sch.slot_conflicts)
                             + " resolved slot conflicts. Retry? (y/grid/quit)? ")
            if line.lower() == "y":
                print("Regenerating schedule.")
                return False
            if line.lower().startswith("grid"):
                sch.print_schedule_grid()
            elif line.lower() == "quit":
                sys.exit(0)
            else:
                print("Unrecognized command. Enter one of y or quit.")

        line = read_line("Enter command (matchups/days/team/grid/write/regen/quit/help): ")
        command = line.lower()
        if command == "write":
            return True
        if command == "regen":
            print("Regenerating schedule.")
            return False

        if command == "quit":
            sys.exit(0)
        elif command.startswith("matchups"):
            if command.strip() == "matchups":
                for t in s.league.get_teams():
                    t.print_schedule_summary(sch)
            else:
                t = team_from_command(s, line)
                if t is not None:
                    t.print_schedule_summary(sch)
        elif command == "days":
            sch.print_schedule_by_day()
        elif command.startswith("team"):
            t = team_from_command(s, line)
            if t is not None:
                t.print_schedule(sch)
        elif command.startswith("grid"):
            sch.print_schedule_grid()
        elif command == "help":
            print(HELP)
        else:
            print("Unrecognized command. Enter one of y, n, or quit.")


def team_from_command(s, line):
    """"team 5", "team T5" or "team t5" -> team 5; None when no team number was given or it doesn't exist."""
    parts = java_split(line, " ")
    if len(parts) <= 1:
        return None
    t_id = int(parts[1].replace("T", "").replace("t", ""))
    return s.get_team_by_id(t_id)


if __name__ == "__main__":
    main(sys.argv[1:])
