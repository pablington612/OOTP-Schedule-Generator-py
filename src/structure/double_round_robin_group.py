from collections import defaultdict

import groovy_math
import scheduler as scheduler_module
from elements.game import Game
from structure.generic_teams_container import GenericTeamsContainer
from structure.round_robin_group import RoundRobinGroup


def _debug():
    return scheduler_module.Scheduler.DEBUG


def _jbool(b):
    return "true" if b else "false"


class DoubleRoundRobinGroup(RoundRobinGroup):
    def __init__(self, group_type, pool, category_cycle_time, subgroups):
        """Use create_with(); this constructor expects pre-built subgroups."""
        super().__init__(pool, category_cycle_time)
        # These are separate from RoundRobinGroup's team columns: this class rotates groups, not teams.
        self.group_right_column = []
        self.group_left_column = []
        self.outside_group = None
        self.current_pairs = []
        self.even_leftovers = False
        self.same_leftovers = False
        self.outside_cycle_size = 0
        self.outside_cycles = 0
        self.inside_rotations_per_outside = 0
        self.inside_rotations_since_outside = 0

        new_subgroups = {}
        for container, teams in subgroups.items():
            new_subgroups[GenericTeamsContainer(container, teams)] = teams
        self.type = group_type
        self.subgroups_map = new_subgroups

        perfect_pool_possible = False
        if len(self.subgroups_map) % 2 == 0:
            all_even = True
            for elements_of_size in self._get_elements_by_size(self.subgroups_map).values():
                if not all_even:
                    break
                all_even = len(elements_of_size) % 2 == 0
            if all_even:
                perfect_pool_possible = True

        if perfect_pool_possible:
            self._fill_columns_matched()
        else:
            self._fill_columns_unmatched()

        self.outside_group = self.group_right_column.pop()
        if _debug():
            print("Left column: " + str(self.group_left_column) + " Right column: " + str(self.group_right_column)
                  + " Outside group: " + str(self.outside_group))
        self._update_pairs()

    @staticmethod
    def create_with(group_type, pool, category_cycle_time):
        subgroups_map = defaultdict(list)
        if group_type == RoundRobinGroup.Type.SUBLEAGUE:
            for t in pool.teams:
                subgroups_map[t.division].append(t)
        else:
            for t in pool.teams:
                subgroups_map[t.division.subleague].append(t)

        if len(subgroups_map) % 2 == 1:
            if _debug():
                print("Size " + str(len(subgroups_map)) + " is invalid for double round robin")
            return None

        largest_subgroup = 0
        for l in subgroups_map.values():
            if len(l) > largest_subgroup:
                largest_subgroup = len(l)
        if _debug():
            print("Double round robin group has " + str(largest_subgroup) + " as its largest subgroup")

        group = DoubleRoundRobinGroup(group_type, pool, category_cycle_time, subgroups_map)
        group.inside_rotations_per_outside = largest_subgroup - 1
        group.even_leftovers = True
        group.same_leftovers = True

        i = 0
        while i < group.size():
            if _debug():
                print(str(i) + ": " + str(group.current_pairs))

            all_have_same_leftovers = True
            all_have_even_leftovers = True
            same_leftovers = -1
            for pair in group.current_pairs:
                leftovers = pair.leftover_size()
                if _debug():
                    print("This leftovers: " + str(leftovers) + " Other leftovers: " + str(same_leftovers))

                if same_leftovers == -1:
                    same_leftovers = leftovers
                elif leftovers != same_leftovers:
                    if _debug():
                        print("Group has different leftovers: " + str(leftovers) + " vs. " + str(same_leftovers))
                    all_have_same_leftovers = False

                if leftovers % 2 == 1:
                    if _debug():
                        print("Group has non-even leftovers: " + str(leftovers))
                    all_have_even_leftovers = False

            group.even_leftovers = group.even_leftovers and all_have_even_leftovers
            group.same_leftovers = group.same_leftovers and all_have_same_leftovers
            if _debug():
                print("Final criteria: even " + _jbool(group.even_leftovers) + " same " + _jbool(group.same_leftovers))

            if not all_have_same_leftovers and not all_have_even_leftovers:
                if _debug():
                    print("Both criteria failed; double round robin group not supported")
                return None

            group._rotate_outside()
            i += 1

        if _debug():
            print("Double round robin group created for " + str(pool))
        return group

    @staticmethod
    def _get_elements_by_size(subgroups_map):
        entities_by_size = defaultdict(list)
        for container in subgroups_map:
            entities_by_size[len(container.get_teams())].append(container)
        return entities_by_size

    def size(self):
        return len(self.current_pairs) * 2

    def _fill_columns_matched(self):
        self.group_right_column.clear()
        self.group_left_column.clear()
        for elements_of_size in self._get_elements_by_size(self.subgroups_map).values():
            for i in range(0, len(elements_of_size), 2):
                self.group_left_column.append(elements_of_size[i])
                self.group_right_column.append(elements_of_size[i + 1])

    def _fill_columns_unmatched(self):
        lists_by_size = sorted(self.subgroups_map, key=lambda c: -c.size())

        self.group_right_column.clear()
        self.group_left_column.clear()
        for i, container in enumerate(lists_by_size):
            if i % 2 == 0:
                self.group_left_column.append(container)
            else:
                self.group_right_column.append(container)

        left = self.group_left_column
        right = self.group_right_column
        if self.pool.size() % 2 == 0:
            while len(left) > len(right):
                right.append(left.pop())
            while len(right) > len(left):
                left.append(right.pop())
        else:
            while len(left) > len(right) + 1:
                right.append(left.pop())
            while len(right) + 1 > len(left):
                left.append(right.pop())

    def _rotate_outside(self):
        self.group_right_column.insert(0, self.group_left_column.pop(0))
        self.group_left_column.append(self.group_right_column.pop())
        self.outside_cycles += 1
        self._update_pairs()

    def _update_pairs(self):
        self.current_pairs.clear()
        for i in range(len(self.group_right_column)):
            self.current_pairs.append(SubgroupPair(self.group_right_column[i], self.group_left_column[i]))
        inside_group = self.group_left_column[len(self.group_right_column)]
        self.current_pairs.append(SubgroupPair(self.outside_group, inside_group))
        self.outside_cycle_size = len(self.current_pairs) - 1

    def _rotate_inside(self):
        for pair in self.current_pairs:
            pair.round_robin.rotate()

    def _step_rotate_inside(self):
        for i, pair in enumerate(self.current_pairs):
            for _ in range(i):
                pair.round_robin.rotate()

    def rotate(self):
        self.right_home = not self.right_home
        if self.inside_rotations_since_outside == self.inside_rotations_per_outside:
            if _debug():
                print("Rotating outside: " + str(self.inside_rotations_since_outside) + " == "
                      + str(self.inside_rotations_per_outside))
            self._rotate_outside()
            self._step_rotate_inside()
            self.inside_rotations_since_outside = 0
        else:
            if _debug():
                print("Rotating inside: " + str(self.inside_rotations_since_outside) + " < "
                      + str(self.inside_rotations_per_outside))
            self._rotate_inside()
            self.inside_rotations_since_outside += 1

    def get_matchups(self):
        matchups = []
        for pair in self.current_pairs:
            matchups.extend(pair.round_robin.get_main_matchups())
        if _debug():
            print("Getting matchups: " + str(matchups))

        if self.same_leftovers:
            left_side = None
            for pair in self.current_pairs:
                if pair.leftover_size() > 0:
                    if left_side is None:
                        left_side = list(pair.leftovers())
                    else:
                        right_side = list(reversed(pair.leftovers()))
                        if _debug():
                            print("Left leftovers: " + str(left_side) + " Right leftovers: " + str(right_side))
                        if len(right_side) != len(left_side):
                            raise RuntimeError("leftover sizes differ")

                        for j in range(len(left_side)):
                            g = Game()
                            if self.right_home:
                                g.home = right_side[j]
                                g.away = left_side[j]
                            else:
                                g.home = left_side[j]
                                g.away = right_side[j]
                            matchups.append(g)
                        left_side = None
        else:
            if not self.even_leftovers:
                raise RuntimeError("???")
            for pair in self.current_pairs:
                matchups.extend(pair.round_robin.get_leftover_matchups())
        return matchups

    def copy_series(self, destination, template):
        self._copy_matchups(destination, template)
        return True


class SubgroupPair:
    def __init__(self, group1, group2):
        self.group1 = group1
        self.group2 = group2
        self.round_robin = ColumnRoundRobinWithLeftovers(group1, group2)

    def __str__(self):
        return "Pair:[" + str(self.group1) + " v. " + str(self.group2) + "]"

    __repr__ = __str__

    def leftovers(self):
        return self.round_robin.leftovers()

    def leftover_size(self):
        return len(self.leftovers())


class ColumnRoundRobinWithLeftovers:
    def __init__(self, group1, group2):
        self.right_home = False
        if len(group1.get_teams()) <= len(group2.get_teams()):
            self.left_column = list(group1.get_teams())
            self.right_column = list(group2.get_teams())
        else:
            self.left_column = list(group2.get_teams())
            self.right_column = list(group1.get_teams())

    def rotate(self):
        self.right_home = not self.right_home
        self.right_column.insert(0, self.right_column.pop())

    def leftovers(self):
        return self.right_column[len(self.left_column):]

    def get_main_matchups(self):
        games = []
        if _debug():
            print("Columns: " + str(self.left_column) + " " + str(self.right_column))
        for i in range(len(self.left_column)):
            g = Game()
            if self.right_home:
                g.home = self.right_column[i]
                g.away = self.left_column[i]
            else:
                g.home = self.left_column[i]
                g.away = self.right_column[i]
            games.append(g)
        return games

    def get_leftover_matchups(self):
        games = []
        if _debug():
            print("Leftovers: " + str(self.leftovers()))

        # Groovy: (size / 2 - 1) as int, with "/" giving a decimal and the cast truncating toward zero.
        half = int(groovy_math.div(len(self.leftovers()), 2) - 1)
        lower_midpoint = half
        upper_midpoint = half + 1
        for i in range(half + 1):
            lower = lower_midpoint - i
            upper = upper_midpoint + i
            g = Game()
            if self.right_home:
                g.home = self.leftovers()[lower]
                g.away = self.leftovers()[upper]
            else:
                g.home = self.leftovers()[upper]
                g.away = self.leftovers()[lower]
            games.append(g)
        return games
