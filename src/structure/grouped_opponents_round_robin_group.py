from collections import defaultdict

from elements.game import Game
from structure.round_robin_group import RoundRobinGroup


class GroupedOpponentsRoundRobinGroup(RoundRobinGroup):
    def __init__(self, group_type, pool, category_cycle_time, matched_mode):
        super().__init__(pool, category_cycle_time)
        self.division_map = defaultdict(list)
        self.subleague_map = defaultdict(list)
        self.type = group_type
        self.took_over = False
        if group_type == RoundRobinGroup.Type.SUBLEAGUE:
            for t in pool.teams:
                self.division_map[t.division].append(t)
            self.active_map = self.division_map
        else:
            for t in pool.teams:
                self.subleague_map[t.division.subleague].append(t)
            self.active_map = self.subleague_map

        perfect_pool_possible = False
        if len(self.active_map) % 2 == 0:
            all_even = True
            for elements_of_size in self._get_elements_by_size().values():
                if not all_even:
                    break
                all_even = len(elements_of_size) % 2 == 0
            if all_even:
                perfect_pool_possible = True

        if matched_mode or perfect_pool_possible:
            self._fill_columns_matched()
        else:
            self._fill_columns_unmatched()

    def _get_elements_by_size(self):
        entities_by_size = defaultdict(list)
        for container, teams in self.active_map.items():
            entities_by_size[len(teams)].append(container)
        return entities_by_size

    def _fill_columns_matched(self):
        self.took_over = True
        self.right_column.clear()
        self.left_column.clear()
        for elements_of_size in self._get_elements_by_size().values():
            for i in range(0, len(elements_of_size), 2):
                self.left_column.extend(self.active_map[elements_of_size[i]])
                self.right_column.extend(self.active_map[elements_of_size[i + 1]])

    def _fill_columns_unmatched(self):
        lists_by_size = [[]] + list(self.active_map.values())
        lists_by_size.sort(key=lambda l: -len(l))

        self.right_column.clear()
        self.left_column.clear()
        for i, teams in enumerate(lists_by_size):
            if i % 2 == 0:
                self.left_column.extend(teams)
            else:
                self.right_column.extend(teams)

        if self.pool.size() % 2 == 0:
            self.took_over = True
            while len(self.left_column) > len(self.right_column):
                self.right_column.append(self.left_column.pop())
            while len(self.right_column) > len(self.left_column):
                self.left_column.append(self.right_column.pop())
        else:
            while len(self.left_column) > len(self.right_column) + 1:
                self.right_column.append(self.left_column.pop())
            while len(self.right_column) + 1 > len(self.left_column):
                self.left_column.append(self.right_column.pop())

    def rotate(self):
        if self.took_over:
            self.right_home = not self.right_home
            if self.pool.size() % 2 == 0:
                self.right_column.append(self.right_column.pop(0))
        else:
            super().rotate()

    def get_matchups(self):
        if not self.took_over:
            return super().get_matchups()

        games = []
        # As in the original, a taken-over group with an odd pool produces no matchups.
        if self.pool.size() % 2 == 0:
            for i in range(len(self.right_column)):
                g = Game()
                if self.right_home:
                    g.home = self.right_column[i]
                    g.away = self.left_column[i]
                else:
                    g.home = self.left_column[i]
                    g.away = self.right_column[i]
                games.append(g)
        return games
