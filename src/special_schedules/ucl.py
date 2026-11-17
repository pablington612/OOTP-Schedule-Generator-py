import os
import random
import re
from datetime import datetime

from elements.day import Day

def generate_random_ucl_schedule(num_pots=4, teams_per_pot=6, play_own_pot=False):
    total_teams = num_pots * teams_per_pot
    schedule = {i: [] for i in range(1, total_teams + 1)}
    
    # Define the pots dynamically based on inputs
    pots = []
    for p in range(num_pots):
        start = p * teams_per_pot + 1
        end = start + teams_per_pot
        pots.append(list(range(start, end)))
    
    # 1. Intra-Pot Matches (Playing against your own pot)
    if play_own_pot:
        for pot in pots:
            shuffled_pot = pot[:]
            random.shuffle(shuffled_pot)
            for t in range(teams_per_pot):
                home_team = shuffled_pot[t]
                away_team = shuffled_pot[(t + 1) % teams_per_pot]
                
                schedule[home_team].append(f"vs Team {away_team} (HOME)")
                schedule[away_team].append(f"vs Team {home_team} (AWAY)")
            
    # 2. Inter-Pot Matches (Playing against the other pots)
    for p_a in range(num_pots):
        for p_b in range(p_a + 1, num_pots):
            pot_a = pots[p_a]
            pot_b = pots[p_b]
            
            # We need two different shuffled lists of Pot B.
            # One for Pot A's home games, one for Pot A's away games.
            while True:
                b_home_opps = pot_b[:]
                b_away_opps = pot_b[:]
                random.shuffle(b_home_opps)
                random.shuffle(b_away_opps)
                
                # Check for duplicates (e.g., Team A plays Team B both Home and Away)
                conflict = any(b_home_opps[k] == b_away_opps[k] for k in range(teams_per_pot))
                if not conflict:
                    break
            
            # Assign the randomized matches
            for k in range(teams_per_pot):
                team_a = pot_a[k]
                team_b_home = b_home_opps[k]
                team_b_away = b_away_opps[k]
                
                # Match 1: Team A at Home
                schedule[team_a].append(f"vs Team {team_b_home} (HOME)")
                schedule[team_b_home].append(f"vs Team {team_a} (AWAY)")
                
                # Match 2: Team A Away
                schedule[team_a].append(f"vs Team {team_b_away} (AWAY)")
                schedule[team_b_away].append(f"vs Team {team_a} (HOME)")

    return schedule

def export_to_xml_hybrid_repair(team_schedules, target_days):
    unique_matches = []
    seen_games = set()
    
    # 1. Extract all unique matches
    for team, games in team_schedules.items():
        for game in games:
            match = re.search(r"vs Team (\d+) \((HOME|AWAY)\)", game)
            if match:
                opponent = int(match.group(1))
                venue = match.group(2)
                
                if venue == "HOME":
                    home, away = team, opponent
                else:
                    home, away = opponent, team
                    
                if (home, away) not in seen_games:
                    seen_games.add((home, away))
                    unique_matches.append((home, away))

    total_days = target_days
    
    while True:
        days = {d: [] for d in range(1, total_days + 1)}
        teams_playing_on_day = {d: set() for d in range(1, total_days + 1)}
        unplaced = []
        
        # PHASE 1: Greedy Allocation
        # Instantly lock in 90%+ of the schedule perfectly
        for home, away in unique_matches:
            placed = False
            for d in range(1, total_days + 1):
                if home not in teams_playing_on_day[d] and away not in teams_playing_on_day[d]:
                    days[d].append((home, away))
                    teams_playing_on_day[d].add(home)
                    teams_playing_on_day[d].add(away)
                    placed = True
                    break
            
            if not placed:
                unplaced.append((home, away))
                
        # PHASE 2: Repair Heuristic (Automated Sudoku Swapping)
        max_repairs = 10000
        repairs = 0
        
        while unplaced and repairs < max_repairs:
            repairs += 1
            home, away = unplaced.pop(0)
            
            # Find a matchday that causes the minimum number of cascading conflicts.
            # We prefer a day where only one team is busy (1-for-1 swap) over a day where both are busy.
            best_days = []
            for test_d in range(1, total_days + 1):
                conflict_count = (home in teams_playing_on_day[test_d]) + (away in teams_playing_on_day[test_d])
                if conflict_count <= 1:
                    best_days.append(test_d)
            
            # Pick a target day (favoring minimal disruption)
            d = random.choice(best_days) if best_days else random.randint(1, total_days)
            
            # Identify the specific games currently blocking our teams on day 'd'
            conflicts = []
            for existing_match in days[d]:
                e_home, e_away = existing_match
                if e_home == home or e_home == away or e_away == home or e_away == away:
                    conflicts.append(existing_match)
                    
            # Eject the conflicting games back into the unplaced queue
            for c in conflicts:
                days[d].remove(c)
                teams_playing_on_day[d].remove(c[0])
                teams_playing_on_day[d].remove(c[1])
                unplaced.append(c)
                
            # Insert our residual game into the newly cleared slot
            days[d].append((home, away))
            teams_playing_on_day[d].add(home)
            teams_playing_on_day[d].add(away)
            
        # If the queue is empty, the schedule is perfect!
        if not unplaced:
            break 
            
        # FAIL-SAFE: If the loop hits 10,000 repairs, the graph is mathematically "Class 2" 
        # and physically cannot be solved in the current number of days. Signal the caller to regenerate.
        return None

    # 3. Format the XML output
    xml_lines = []
    for d in range(1, total_days + 1):
        if len(days[d]) > 0:
            xml_lines.append("")
            for home, away in days[d]:
                xml_lines.append(f'<GAME day="{d}" time="1900" away="{away}" home="{home}" type="0"/>')
            
    return "\n".join(xml_lines)

def run(pots_to_use=4, teams_in_each_pot=9, include_own_pot=True, start_day_of_week="Wednesday"):
    # Calculate expected matches based on settings (own pot adds 2 matches)
    matches_per_team = ((pots_to_use - 1) * 2) + (2 if include_own_pot else 0)

    attempts = 0
    while True:
        attempts += 1
        team_schedules = generate_random_ucl_schedule(
            num_pots=pots_to_use,
            teams_per_pot=teams_in_each_pot,
            play_own_pot=include_own_pot
        )
        xml_output = export_to_xml_hybrid_repair(team_schedules, target_days=matches_per_team)
        if xml_output is not None:
            break
        print(f"Attempt {attempts} failed to fit in {matches_per_team} matchdays. Retrying...")

    # Same timestamp format as ootp_schedule_file_writer.write_schedule_file.
    now = datetime.now()
    timestamp = "%04d" % now.isocalendar()[0] + now.strftime("%m%d%H%M%S")
    filename = f"UCL_P{pots_to_use}_T{teams_in_each_pot}_G{matches_per_team}_C_autogen{timestamp}.lsdl"
    ootp_day = Day.day_code_to_ootp_day_code(Day.string_to_day_code(start_day_of_week))

    contents = ['<?xml version="1.0" encoding="ISO-8859-1"?>\n',
                f'<SCHEDULE type="{filename}" inter_league="0" balanced_games="0" '
                f'games_per_team="{matches_per_team}" start_day_of_week="{ootp_day}" >\n',
                "<GAMES>\n",
                xml_output + "\n",
                "</GAMES>\n",
                "</SCHEDULE>\n"]
    with open(os.path.join(".", filename), "w", encoding="iso-8859-1", newline="\n") as f:
        f.write("".join(contents))

    print(filename)
    print(f"Process completed in {attempts} attempts.")