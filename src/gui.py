import os
import queue
import sys
import threading
import time
import tkinter as tk
import traceback
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import team_from_command  # noqa: E402
from ootp_schedule_file_writer import write_schedule_file  # noqa: E402
from scheduler import Scheduler  # noqa: E402

DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

# (section, key, kind, default); kind is "bool", "text", "day", or "days".
FIELDS = [
    ("general", "interleague", "bool", False),
    ("general", "balanced", "bool", True),
    ("general", "structure", "text", "SL1_D1_T16"),
    ("schedule", "divisional_games", "text", "60"),
    ("schedule", "subleague_games", "text", "0"),
    ("schedule", "interleague_games", "text", "0"),
    ("schedule", "match_divisions", "bool", False),
    ("schedule", "match_subleagues", "bool", False),
    ("schedule", "match_subleagues_by_division", "bool", False),
    ("divisional-series", "preferred_length", "text", "2"),
    ("divisional-series", "pool_count", "text", "1"),
    ("subleague-series", "preferred_length", "text", "2"),
    ("subleague-series", "pool_count", "text", "1"),
    ("interleague-series", "preferred_length", "text", "1"),
    ("interleague-series", "pool_count", "text", "1"),
    ("break", "break_days", "text", "0"),
    ("break", "all_star_percentage", "text", "-1"),
    ("break", "all_star_length", "text", "6"),
    ("break", "all_star_day_of_week", "day", "none"),
    ("break", "start_day_of_week", "day", "Saturday"),
    ("break", "off_days_of_week", "days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]),
    ("break", "non_off_days_of_week", "days", ["Saturday", "Sunday"]),
    ("break", "mid_series_breaks", "bool", False),
    ("time", "first_start", "text", "1800"),
    ("time", "last_start", "text", "2000"),
    ("time", "start_offset", "text", "5"),
    ("time", "simultaneous_games", "text", "2"),
]


class QueueWriter:
    """Stands in for sys.stdout; the Tk loop drains the queue into the log pane."""

    def __init__(self, q):
        self.q = q

    def write(self, text):
        self.q.put(text)

    def flush(self):
        pass


class App:
    def __init__(self, root):
        self.root = root
        root.title("OOTP Schedule Generator")
        self.vars = {}
        self.s = None
        self.sch = None
        self.out = queue.Queue()
        sys.stdout = QueueWriter(self.out)

        tabs = ttk.Notebook(root)
        tabs.pack(fill="x", padx=8, pady=8)
        frames = {}
        for section, key, kind, default in FIELDS:
            if section not in frames:
                frames[section] = ttk.Frame(tabs, padding=8)
                tabs.add(frames[section], text=section)
            self._add_field(frames[section], section, key, kind, default)

        bar = ttk.Frame(root, padding=(8, 0))
        bar.pack(fill="x")
        self.debug = tk.BooleanVar(value=False)
        self.generate_btn = ttk.Button(bar, text="Generate", command=self.generate)
        self.generate_btn.pack(side="left")
        ttk.Checkbutton(bar, text="Debug", variable=self.debug).pack(side="left", padx=(4, 12))
        self.team = tk.StringVar()
        ttk.Label(bar, text="Team #").pack(side="left")
        ttk.Entry(bar, textvariable=self.team, width=5).pack(side="left", padx=(2, 8))
        self.matchups_btn = ttk.Button(bar, text="Matchups", command=lambda: self.run(self.matchups, self.team.get().strip()))
        self.team_btn = ttk.Button(bar, text="Team", command=lambda: self.run(self.team_schedule, self.team.get().strip()))
        self.days_btn = ttk.Button(bar, text="Days", command=lambda: self.run(lambda: self.sch.print_schedule_by_day()))
        self.grid_btn = ttk.Button(bar, text="Grid", command=lambda: self.run(lambda: self.sch.print_schedule_grid()))
        self.write_btn = ttk.Button(bar, text="Write", command=lambda: self.run(lambda: write_schedule_file(self.s, self.sch)))
        for b in (self.matchups_btn, self.team_btn, self.days_btn, self.grid_btn, self.write_btn):
            b.pack(side="left", padx=2)
        ttk.Button(bar, text="Clear log", command=lambda: self.log.delete("1.0", "end")).pack(side="right")

        self.log = ScrolledText(root, font=("Consolas", 10), height=30, width=120)
        self.log.pack(fill="both", expand=True, padx=8, pady=8)

        self.set_buttons(busy=False)
        self.drain()

    def _add_field(self, frame, section, key, kind, default):
        row = frame.grid_size()[1]
        ttk.Label(frame, text=key).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
        if kind == "bool":
            var = tk.BooleanVar(value=default)
            ttk.Checkbutton(frame, variable=var).grid(row=row, column=1, sticky="w")
        elif kind == "text":
            var = tk.StringVar(value=default)
            ttk.Entry(frame, textvariable=var, width=20).grid(row=row, column=1, sticky="w")
        elif kind == "day":
            var = tk.StringVar(value=default)
            ttk.Combobox(frame, textvariable=var, values=["none"] + DAYS, state="readonly",
                         width=12).grid(row=row, column=1, sticky="w")
        else:
            var = {d: tk.BooleanVar(value=d in default) for d in DAYS}
            box = ttk.Frame(frame)
            box.grid(row=row, column=1, sticky="w")
            for d in DAYS:
                ttk.Checkbutton(box, text=d[:3], variable=var[d]).pack(side="left")
        self.vars[(section, key)] = (kind, var)

    def collect_settings(self):
        """Same shape IniLoader.load() returns: {section: {key: str or list}}."""
        settings = {}
        for (section, key), (kind, var) in self.vars.items():
            if kind == "bool":
                value = "true" if var.get() else "false"
            elif kind == "days":
                value = [d for d in DAYS if var[d].get()]
            else:
                value = var.get().strip()
            if kind == "day" and value == "none":
                continue
            settings.setdefault(section, {})[key] = value
        return settings

    def set_buttons(self, busy):
        have = self.sch is not None and not busy
        ok = have and self.sch.success
        self.generate_btn.config(state="disabled" if busy else "normal",
                                 text="Regen" if self.sch is not None else "Generate")
        for b in (self.matchups_btn, self.team_btn, self.days_btn, self.write_btn):
            b.config(state="normal" if ok else "disabled")
        self.grid_btn.config(state="normal" if have else "disabled")

    def run(self, action, *args):
        """Runs action on a worker thread, logging any error instead of crashing."""
        self.set_buttons(busy=True)

        def work():
            try:
                action(*args)
            except BaseException:
                traceback.print_exc(file=sys.stdout)
            self.out.put(lambda: self.set_buttons(busy=False))  # run on the Tk thread by drain()

        threading.Thread(target=work, daemon=True).start()

    def generate(self):
        settings = self.collect_settings()
        debug = self.debug.get()

        def action():
            self.sch = None
            s = Scheduler()
            s.load_settings(settings)
            Scheduler.DEBUG = debug
            start_time = int(time.time() * 1000)
            sch = s.schedule()
            total_time = (int(time.time() * 1000) - start_time) / 1000.0
            print("Scheduled " + str(sch.total_series_scheduled) + " series (" + str(sch.total_games_scheduled)
                  + " games) in " + str(total_time) + " seconds")
            rate = sch.total_series_scheduled / total_time if total_time else float("inf")
            print(str(rate) + " series/sec")
            if not sch.success:
                print("Scheduling failed with " + str(sch.slot_conflicts)
                      + " resolved slot conflicts. Regen to retry.")
            self.s, self.sch = s, sch

        self.run(action)

    def selected_team(self, team):
        t = team_from_command(self.s, "team " + team)
        if t is None:
            print("No such team: '" + team + "'")
        return t

    def matchups(self, team):
        if not team:
            for t in self.s.league.get_teams():
                t.print_schedule_summary(self.sch)
        else:
            t = self.selected_team(team)
            if t is not None:
                t.print_schedule_summary(self.sch)

    def team_schedule(self, team):
        t = self.selected_team(team)
        if t is not None:
            t.print_schedule(self.sch)

    def drain(self):
        while not self.out.empty():
            item = self.out.get_nowait()
            if callable(item):
                item()
            else:
                self.log.insert("end", item)
                self.log.see("end")
        self.root.after(50, self.drain)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
