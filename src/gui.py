import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
import traceback
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ini_loader import IniLoader  # noqa: E402
from main import team_from_command  # noqa: E402
from ootp_schedule_file_writer import write_schedule_file  # noqa: E402
from scheduler import Scheduler  # noqa: E402
from special_schedules.ucl import run as run_ucl  # noqa: E402

UCL = "UCL Style League Phase"
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAD = 8

DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

TABS = {
    "general": "General",
    "schedule": "Schedule",
    "divisional-series": "Divisional Series",
    "subleague-series": "Subleague Series",
    "interleague-series": "Interleague Series",
    "break": "Breaks",
    "time": "Game Times",
}

SERIES_LENGTH_TIP = "Preferred number of games per series."
POOL_COUNT_TIP = "Teams in each division (or subleague, or the whole league) are split into this many pools."

# (section, key, label, kind, default, tooltip); section/key are the setting names Scheduler reads,
# label is the text shown; kind is "bool", "int", "day", or "days".
FIELDS = [
    ("general", "interleague", "Interleague play", "bool", False,
     "Only affects the schedule file's name and header. To actually schedule interleague games, "
     "use Interleague games on the Schedule tab."),
    ("general", "balanced", "Balanced schedule", "bool", True,
     "Only affects the schedule file's name and header, claiming the schedule is balanced."),
    ("schedule", "divisional_games", "Divisional games", "int", 60,
     "Games each team plays against its own division."),
    ("schedule", "subleague_games", "Subleague games", "int", 0,
     "Games each team plays against the rest of its subleague."),
    ("schedule", "interleague_games", "Interleague games", "int", 0,
     "Games each team plays against the other subleague (interleague/interdivisional)."),
    ("schedule", "match_divisions", "Match divisions", "bool", False,
     "Try to set up interdivisional pools between divisions of the same size."),
    ("schedule", "match_subleagues", "Match subleagues", "bool", False,
     "Try to set up interleague pools between subleagues of the same size."),
    ("schedule", "match_subleagues_by_division", "Match subleagues by division", "bool", False,
     "Try to set up interleague pools between divisions of the same size. "
     "If Match subleagues is also on, it takes priority."),
    ("divisional-series", "preferred_length", "Preferred series length", "int", 2, SERIES_LENGTH_TIP),
    ("divisional-series", "pool_count", "Pool count", "int", 1, POOL_COUNT_TIP),
    ("subleague-series", "preferred_length", "Preferred series length", "int", 2, SERIES_LENGTH_TIP),
    ("subleague-series", "pool_count", "Pool count", "int", 1, POOL_COUNT_TIP),
    ("interleague-series", "preferred_length", "Preferred series length", "int", 1, SERIES_LENGTH_TIP),
    ("interleague-series", "pool_count", "Pool count", "int", 1, POOL_COUNT_TIP),
    ("break", "break_days", "Break days", "int", 0,
     "This many days of break/padding are added over the course of the season."),
    ("break", "all_star_percentage", "All-Star break at % of season", "int", -1,
     "The All-Star game is scheduled this far into the season. -1 disables All-Star scheduling."),
    ("break", "all_star_length", "All-Star break length (days)", "int", 6,
     "The All-Star game occurs in a break of this length."),
    ("break", "all_star_day_of_week", "All-Star break day", "day", "none",
     "Day of the week the All-Star game occurs on."),
    ("break", "start_day_of_week", "Season start day", "day", "Saturday",
     "First day of the week in the schedule (enables week-aware scheduling)."),
    ("break", "off_days_of_week", "Off days", "days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
     "No games will be scheduled on these days."),
    ("break", "non_off_days_of_week", "Never-off days", "days", ["Saturday", "Sunday"],
     "No random break days will be placed on these days."),
    ("break", "mid_series_breaks", "Allow mid-series breaks", "bool", False,
     "If off, break days are moved to the end of series, unless that would put a game on a never-off day."),
    ("time", "first_start", "Earliest start time", "int", 1800,
     "Schedule the first game of a day no earlier than this (24h, e.g. 1800)."),
    ("time", "last_start", "Latest start time", "int", 2000,
     "Schedule the last game of a day no later than this (24h, e.g. 2000)."),
    ("time", "start_offset", "Start time offset", "int", 5,
     "Offset start times from the hour and half-hour by this many minutes."),
    ("time", "simultaneous_games", "Simultaneous games", "int", 2,
     "Start this many games at the same time."),
]

# key -> (lo, hi, step) for "int" fields.
BOUNDS = {
    "divisional_games": (0, 999, 1),
    "subleague_games": (0, 999, 1),
    "interleague_games": (0, 999, 1),
    "preferred_length": (1, 10, 1),
    "pool_count": (1, 50, 1),
    "break_days": (0, 365, 1),
    "all_star_percentage": (-1, 100, 1),
    "all_star_length": (1, 30, 1),
    "first_start": (0, 2359, 100),
    "last_start": (0, 2359, 100),
    "start_offset": (0, 59, 1),
    "simultaneous_games": (1, 50, 1),
}


class QueueWriter:
    """Stands in for sys.stdout; the Tk loop drains the queue into the log pane."""

    def __init__(self, q):
        self.q = q

    def write(self, text):
        self.q.put(text)

    def flush(self):
        pass


class Tooltip:
    """Shows text in a small popup while the pointer is over widget."""

    def __init__(self, widget, text):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _):
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry("+%d+%d" % (x, y))
        tk.Label(self.tip, text=self.text, justify="left", background="#ffffe0", relief="solid",
                 borderwidth=1, wraplength=320, padx=4, pady=2).pack()

    def hide(self, _):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


class App:
    def __init__(self, root):
        self.root = root
        root.title("OOTP Schedule Generator")
        root.geometry("1000x720")
        root.minsize(760, 520)
        self.vars = {}
        self.s = None
        self.sch = None
        self.out = queue.Queue()
        sys.stdout = QueueWriter(self.out)

        self._add_menu()

        status = ttk.Frame(root, padding=(PAD, 2, PAD, 4))
        status.pack(side="bottom", fill="x")
        self.status = tk.StringVar(value="Ready")
        ttk.Label(status, textvariable=self.status).pack(side="left")
        self.progress = ttk.Progressbar(status, mode="indeterminate", length=160)
        self.progress.pack(side="right")

        paned = ttk.PanedWindow(root, orient="vertical")
        paned.pack(fill="both", expand=True, padx=PAD, pady=(PAD, 0))
        top = ttk.Frame(paned)
        paned.add(top, weight=0)

        tabs = ttk.Notebook(top)
        tabs.pack(fill="x")
        frames = {}
        for section, key, label, kind, default, tip in FIELDS:
            if section not in frames:
                frames[section] = ttk.Frame(tabs, padding=PAD)
                tabs.add(frames[section], text=TABS[section])
            self._add_field(frames[section], section, key, label, kind, default, tip)
        self._add_structure(frames["general"])
        special = ttk.Frame(tabs, padding=PAD)
        tabs.add(special, text="Special Schedules")
        self._add_special(special)

        self._add_toolbar(top)

        log_frame = ttk.Frame(paned)
        paned.add(log_frame, weight=1)
        self.log = ScrolledText(log_frame, font=("Consolas", 10), height=20, width=120, state="disabled")
        self.log.pack(fill="both", expand=True, pady=(PAD, PAD))
        self.log.tag_configure("error", foreground="#c00000")
        self.log.tag_configure("ok", foreground="#007a00")

        root.bind_all("<Control-g>", lambda e: self.generate_btn.invoke())
        root.bind_all("<Control-o>", lambda e: self.open_settings())
        root.bind_all("<Control-s>", lambda e: self.save_settings())
        root.bind_all("<Control-l>", lambda e: self.clear_log())

        self.set_buttons(busy=False)
        self.drain()

    def _add_menu(self):
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="Open settings...", accelerator="Ctrl+O", command=self.open_settings)
        file_menu.add_command(label="Save settings...", accelerator="Ctrl+S", command=self.save_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Save log...", command=self.save_log)
        file_menu.add_command(label="Clear log", accelerator="Ctrl+L", command=self.clear_log)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menu.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menu)

    def _add_toolbar(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(PAD, 0))

        run_box = ttk.LabelFrame(bar, text="Run", padding=(PAD, 4))
        run_box.pack(side="left", fill="y")
        self.debug = tk.BooleanVar(value=False)
        self.generate_btn = ttk.Button(run_box, text="Generate", command=self.generate)
        self.generate_btn.grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(run_box, text="Debug", variable=self.debug).grid(row=0, column=1, padx=PAD)
        self.write_btn = ttk.Button(run_box, text="Write", command=lambda: self.run(
            lambda d: write_schedule_file(self.s, self.sch, d), self.out_dir.get()))
        self.write_btn.grid(row=0, column=2, sticky="w")
        Tooltip(self.write_btn, "Write the schedule file (.lsdl) to the output folder.")
        folder = ttk.Frame(run_box)
        folder.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.out_dir = tk.StringVar(value=os.getcwd())
        ttk.Label(folder, text="Output folder").pack(side="left")
        ttk.Entry(folder, textvariable=self.out_dir, width=32).pack(side="left", padx=4)
        ttk.Button(folder, text="Browse...", command=self.browse_out_dir).pack(side="left")

        view_box = ttk.LabelFrame(bar, text="View", padding=(PAD, 4))
        view_box.pack(side="left", fill="y", padx=PAD)
        self.team = tk.StringVar()
        team_label = ttk.Label(view_box, text="Team #")
        team_label.pack(side="left")
        Tooltip(team_label, "Team number for Matchups/Team. Leave blank in Matchups to show every team.")
        ttk.Entry(view_box, textvariable=self.team, width=5).pack(side="left", padx=(2, PAD))
        self.matchups_btn = ttk.Button(view_box, text="Matchups",
                                       command=lambda: self.run(self.matchups, self.team.get().strip()))
        self.team_btn = ttk.Button(view_box, text="Team",
                                   command=lambda: self.run(self.team_schedule, self.team.get().strip()))
        self.days_btn = ttk.Button(view_box, text="Days", command=lambda: self.run(lambda: self.sch.print_schedule_by_day()))
        self.grid_btn = ttk.Button(view_box, text="Grid", command=lambda: self.run(lambda: self.sch.print_schedule_grid()))
        for b in (self.matchups_btn, self.team_btn, self.days_btn, self.grid_btn):
            b.pack(side="left", padx=2)

        ttk.Button(bar, text="Clear log", command=self.clear_log).pack(side="right", anchor="s")

    def _add_field(self, frame, section, key, label, kind, default, tip):
        row = frame.grid_size()[1]
        lbl = ttk.Label(frame, text=label)
        lbl.grid(row=row, column=0, sticky="w", padx=(0, PAD), pady=2)
        Tooltip(lbl, tip)
        if kind == "bool":
            var = tk.BooleanVar(value=default)
            ttk.Checkbutton(frame, variable=var).grid(row=row, column=1, sticky="w")
        elif kind == "int":
            var = tk.IntVar(value=default)
            lo, hi, step = BOUNDS[key]
            self._spinbox(frame, var, hi, lo, step).grid(row=row, column=1, sticky="w")
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

    @staticmethod
    def _int(var):
        """var's value, or None while the field is blank."""
        try:
            return var.get()
        except tk.TclError:
            return None

    def _spinbox(self, parent, var, hi, lo=1, step=1):
        """Typable lo..hi spinbox: digits only, values over hi snap to hi, blank/under lo snaps to lo on leave."""
        def cap(*_):
            v = self._int(var)
            if v is not None and v > hi:
                var.set(hi)

        def floor(_):
            v = self._int(var)
            if v is None or v < lo:
                var.set(lo)

        def valid(p):
            if lo < 0 and p.startswith("-"):
                p = p[1:]
            return p == "" or p.isdigit()

        var.trace_add("write", cap)
        sb = ttk.Spinbox(parent, from_=lo, to=hi, increment=step, textvariable=var, width=6, validate="key",
                         validatecommand=(parent.register(valid), "%P"))
        sb.bind("<FocusOut>", floor)
        sb.bind("<Return>", floor)
        return sb

    def _add_structure(self, frame):
        """Subleague count, divisions per subleague, and per-division team counts (via edit_divisions)."""
        self.subleagues = tk.IntVar(value=1)
        self.div_counts = [tk.IntVar(value=1), tk.IntVar(value=1)]
        self.div_teams = [[tk.IntVar(value=16)], [tk.IntVar(value=4)]]
        row = frame.grid_size()[1]
        ttk.Separator(frame).grid(row=row, column=0, columnspan=3, sticky="ew", pady=PAD)
        row += 1
        lbl = ttk.Label(frame, text="Subleagues")
        lbl.grid(row=row, column=0, sticky="w", padx=(0, PAD), pady=2)
        Tooltip(lbl, "Number of subleagues (1 or 2).")
        self._spinbox(frame, self.subleagues, 2).grid(row=row, column=1, sticky="w")
        sl_rows = []
        for i in range(2):
            widgets = [
                ttk.Label(frame, text="Divisions in Sub League " + str(i + 1)),
                self._spinbox(frame, self.div_counts[i], 50),
                ttk.Button(frame, text="Edit Sub League " + str(i + 1) + " Divisions",
                           command=lambda i=i: self.edit_divisions(i)),
            ]
            Tooltip(widgets[0], "Number of divisions in this subleague. Set each division's team count "
                                "with the Edit button.")
            for col, w in enumerate(widgets):
                w.grid(row=row + 1 + i, column=col, sticky="w", padx=(0, PAD), pady=2)
            sl_rows.append(widgets)
            self.div_counts[i].trace_add("write", lambda *_, i=i: self._resize_divisions(i))

        def show_subleagues(*_):
            n = self._int(self.subleagues)
            if n is None or n < 1:
                return
            for i, widgets in enumerate(sl_rows):
                for w in widgets:
                    w.grid() if i < n else w.grid_remove()

        self.subleagues.trace_add("write", show_subleagues)
        show_subleagues()

    def _add_special(self, frame):
        """Special schedule picker; UCL options only show while UCL is selected."""
        self.special = tk.StringVar(value="None")
        lbl = ttk.Label(frame, text="Special schedule")
        lbl.grid(row=0, column=0, sticky="w", padx=(0, PAD), pady=2)
        Tooltip(lbl, "When set, Generate builds this schedule instead of using the other tabs, "
                     "and writes it straight to the output folder.")
        ttk.Combobox(frame, textvariable=self.special, values=["None", UCL], state="readonly",
                     width=24).grid(row=0, column=1, sticky="w")

        ucl = ttk.Frame(frame)
        ucl.grid(row=1, column=0, columnspan=2, sticky="w")
        self.ucl_pots = tk.IntVar(value=4)
        self.ucl_teams = tk.IntVar(value=9)
        self.ucl_own_pot = tk.BooleanVar(value=True)
        self.ucl_start_day = tk.StringVar(value="Wednesday")
        rows = [
            ("Pots to use", self._spinbox(ucl, self.ucl_pots, 50), "Number of pots teams are drawn from."),
            ("Teams in each pot", self._spinbox(ucl, self.ucl_teams, 50, lo=2), "Teams per pot."),
            ("Include own pot", ttk.Checkbutton(ucl, variable=self.ucl_own_pot),
             "Teams also play two games against teams from their own pot."),
            ("Start day", ttk.Combobox(ucl, textvariable=self.ucl_start_day, values=DAYS, state="readonly",
                                       width=12), "Day of the week the schedule starts on."),
        ]
        for r, (text, widget, tip) in enumerate(rows):
            lbl = ttk.Label(ucl, text=text)
            lbl.grid(row=r, column=0, sticky="w", padx=(0, PAD), pady=2)
            Tooltip(lbl, tip)
            widget.grid(row=r, column=1, sticky="w")

        def show_ucl(*_):
            ucl.grid() if self.special.get() == UCL else ucl.grid_remove()

        self.special.trace_add("write", show_ucl)
        show_ucl()

    def _resize_divisions(self, i):
        teams = self.div_teams[i]
        n = self._int(self.div_counts[i])
        if n is None or n < 1:  # mid-edit; floor() will write a valid value
            return
        n = min(n, 50)  # cap() clamps the field, but writes made inside a trace don't re-fire traces
        del teams[n:]
        teams.extend(tk.IntVar(value=4) for _ in range(n - len(teams)))

    def edit_divisions(self, i):
        win = tk.Toplevel(self.root)
        win.title("Sub League " + str(i + 1) + " Divisions")
        win.transient(self.root)
        body = ttk.Frame(win, padding=PAD)
        body.pack(fill="both", expand=True)
        for k, var in enumerate(self.div_teams[i]):
            ttk.Label(body, text="Teams in Division " + str(k + 1)).grid(row=k, column=0, sticky="w",
                                                                        padx=(0, PAD), pady=2)
            self._spinbox(body, var, 50).grid(row=k, column=1, sticky="w")
        ttk.Button(body, text="Close", command=win.destroy).grid(row=len(self.div_teams[i]), column=0,
                                                                 columnspan=2, pady=(PAD, 0))
        win.grab_set()

    def structure_string(self):
        """Builds the "SL1_D1_T4_D2_T4" string Scheduler.generate_league_structure parses."""
        parts = []
        div_id = 1
        for i in range(self._int(self.subleagues) or 1):
            parts.append("SL" + str(i + 1))
            for var in self.div_teams[i]:
                parts.append("D" + str(div_id) + "_T" + str(self._int(var) or 1))
                div_id += 1
        return "_".join(parts)

    def apply_structure(self, structure):
        """Inverse of structure_string; clamps to what the GUI can show (2 subleagues, 50 divisions/teams)."""
        subleagues = [[int(t) for t in re.findall(r"D\d*T(\d+)", sl)]
                      for sl in structure.replace("_", "").split("SL") if sl.strip()]
        if len(subleagues) > 2 or any(len(divs) > 50 or max(divs, default=0) > 50 for divs in subleagues):
            self.out.put(("Warning: structure clamped to 2 subleagues and 50 divisions/teams.\n", "error"))
        subleagues = [divs[:50] for divs in subleagues[:2]]
        self.subleagues.set(len(subleagues))
        for i, divs in enumerate(subleagues):
            self.div_counts[i].set(len(divs))
            for var, teams in zip(self.div_teams[i], divs):
                var.set(min(teams, 50))

    def collect_settings(self):
        """Same shape IniLoader.load() returns: {section: {key: str or list}}."""
        settings = {}
        for (section, key), (kind, var) in self.vars.items():
            if kind == "bool":
                value = "true" if var.get() else "false"
            elif kind == "days":
                value = [d for d in DAYS if var[d].get()]
            elif kind == "int":
                lo, hi, _ = BOUNDS[key]
                v = self._int(var)
                value = str(lo if v is None else min(max(v, lo), hi))
            else:
                value = var.get().strip()
            if kind == "day" and value == "none":
                continue
            settings.setdefault(section, {})[key] = value
        settings["general"]["structure"] = self.structure_string()
        return settings

    def apply_settings(self, settings):
        """Fills the form from IniLoader.load() output; missing day settings reset to none/unchecked."""
        for (section, key), (kind, var) in self.vars.items():
            value = settings.get(section, {}).get(key)
            if kind == "days":
                for d in DAYS:
                    var[d].set(d in (value or []))
            elif kind == "day":
                var.set(value or "none")
            elif value is None:
                continue
            elif kind == "bool":
                var.set(str(value).lower() == "true")
            else:
                var.set(int(value))
        structure = settings.get("general", {}).get("structure")
        if structure:
            self.apply_structure(structure)

    def open_settings(self):
        path = filedialog.askopenfilename(initialdir=PROJECT_DIR, filetypes=[("Settings", "*.ini"), ("All files", "*")])
        if not path:
            return
        try:
            self.apply_settings(IniLoader(path).load())
            self.out.put(("Loaded settings from " + path + "\n", "ok"))
        except Exception:
            self.out.put((traceback.format_exc(), "error"))

    def save_settings(self):
        path = filedialog.asksaveasfilename(initialdir=PROJECT_DIR, defaultextension=".ini",
                                            filetypes=[("Settings", "*.ini")])
        if not path:
            return
        lines = []
        for section, values in self.collect_settings().items():
            lines.append("[" + section + "]")
            for key, value in values.items():
                if isinstance(value, list):
                    if not value:  # IniLoader can't read an empty list; a missing key means none
                        continue
                    value = "List:" + "|".join(value)
                lines.append(key + "=" + value)
            lines.append("")
        with open(path, "w") as f:
            f.write("\n".join(lines))
        self.out.put(("Saved settings to " + path + "\n", "ok"))

    def save_log(self):
        path = filedialog.asksaveasfilename(initialdir=self.out_dir.get(), defaultextension=".txt",
                                            filetypes=[("Text", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.log.get("1.0", "end"))

    def clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def browse_out_dir(self):
        path = filedialog.askdirectory(initialdir=self.out_dir.get())
        if path:
            self.out_dir.set(path)

    def set_buttons(self, busy, status=None):
        have = self.sch is not None and not busy
        ok = have and self.sch.success
        self.generate_btn.config(state="disabled" if busy else "normal",
                                 text="Regen" if self.sch is not None else "Generate")
        for b in (self.matchups_btn, self.team_btn, self.days_btn, self.write_btn):
            b.config(state="normal" if ok else "disabled")
        self.grid_btn.config(state="normal" if have else "disabled")
        if busy:
            self.progress.start(10)
            self.status.set("Working...")
        else:
            self.progress.stop()
            if status:
                self.status.set(status)

    def run(self, action, *args):
        """Runs action on a worker thread, logging any error instead of crashing.
        action may return a status-bar message; otherwise the status reads "Done"."""
        self.set_buttons(busy=True)

        def work():
            try:
                status = action(*args) or "Done"
            except BaseException:
                self.out.put((traceback.format_exc(), "error"))
                status = "Error (see log)"
            self.out.put(lambda: self.set_buttons(busy=False, status=status))  # run on the Tk thread by drain()

        threading.Thread(target=work, daemon=True).start()

    def generate(self):
        out_dir = self.out_dir.get()
        if self.special.get() == UCL:
            args = (self._int(self.ucl_pots) or 1, max(self._int(self.ucl_teams) or 0, 2), self.ucl_own_pot.get(),
                    self.ucl_start_day.get(), out_dir)

            def ucl_action():
                self.sch = None
                run_ucl(*args)

            self.run(ucl_action)
            return

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
            self.out.put(("Scheduled " + str(sch.total_series_scheduled) + " series (" + str(sch.total_games_scheduled)
                          + " games) in " + str(total_time) + " seconds\n", "ok"))
            rate = sch.total_series_scheduled / total_time if total_time else float("inf")
            print(str(rate) + " series/sec")
            self.s, self.sch = s, sch
            if not sch.success:
                self.out.put(("Scheduling failed with " + str(sch.slot_conflicts)
                              + " resolved slot conflicts. Regen to retry.\n", "error"))
                return "Scheduling failed - Regen to retry"

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
        if not self.out.empty():
            self.log.config(state="normal")
            while not self.out.empty():
                item = self.out.get_nowait()
                if callable(item):
                    item()
                else:
                    text, tag = item if isinstance(item, tuple) else (item, ())
                    self.log.insert("end", text, tag)
            self.log.config(state="disabled")
            self.log.see("end")
        self.root.after(50, self.drain)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
