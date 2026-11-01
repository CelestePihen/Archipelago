import unittest

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive
from Options import OptionError
from test.general import setup_multiworld
from worlds.smg.items import ITEM
from worlds.smg.options import RequiredStars, max_required_stars
from worlds.smg.world import SMGWorld


class GenerationLimitTests(unittest.TestCase):
    def assert_fill_reachable(self, multiworld):
        distribute_items_restrictive(multiworld)
        remaining = set(multiworld.get_locations())
        state = CollectionState(multiworld)
        while remaining:
            sphere = {loc for loc in remaining if loc.can_reach(state)}
            self.assertTrue(sphere, f"Unreachable checks: {remaining}")
            remaining -= sphere
            for loc in sphere:
                self.assertIsNotNone(loc.item)
                state.collect(loc.item, True, loc)
        self.assertTrue(multiworld.has_beaten_game(state))

    def test_range_rejects_oversized_values(self):
        for value in (0, 79, 121):
            with self.subTest(value=value), self.assertRaisesRegex(Exception, r"minimum|maximum"):
                RequiredStars.from_any(value)

    def test_individual_limit_fails_before_creating_regions_or_items(self):
        for required in (74, 78):
            multiworld = setup_multiworld(
                SMGWorld, steps=(), seed=1,
                options={"dome_unlock_mode": 1, "required_stars": required},
            )
            with self.assertRaisesRegex(OptionError, r"maximum of 73.*individual"):
                multiworld.worlds[1].generate_early()
            self.assertFalse(multiworld.regions)
            self.assertFalse(multiworld.itempool)
            self.assertFalse(multiworld.precollected_items[1])

    def test_boundary_pools_fill_and_all_checks_are_reachable(self):
        for mode, maximum in ((0, 78), (1, 73)):
            self.assertEqual(max_required_stars(mode), maximum)
            for required in (1, 3, maximum - 1, maximum):
                for seed in range(5):
                    with self.subTest(mode=mode, required=required, seed=seed):
                        multiworld = setup_multiworld(
                            SMGWorld, seed=seed,
                            options={"dome_unlock_mode": mode, "required_stars": required},
                        )
                        self.assertEqual(len(multiworld.itempool), 120)
                        self.assertEqual(sum(i.name == ITEM.Star for i in multiworld.itempool), required)
                        self.assertEqual(sum(i.name == ITEM.Coin for i in multiworld.itempool), maximum - required + 1)
                        self.assert_fill_reachable(multiworld)
                        self.assertEqual(multiworld.get_location("Bowser's Galaxy Reactor 1", 1).item.name, ITEM.Coin)

    def test_mixed_multiworld_at_both_limits(self):
        for seed in range(5):
            with self.subTest(seed=seed):
                multiworld = setup_multiworld(
                    [SMGWorld, SMGWorld], seed=seed,
                    options=[{"dome_unlock_mode": 0, "required_stars": 78},
                             {"dome_unlock_mode": 1, "required_stars": 73}],
                )
                self.assert_fill_reachable(multiworld)


if __name__ == "__main__":
    unittest.main()
