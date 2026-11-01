import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld
from worlds.smg.items import ITEM
from worlds.smg.regions import GALAXY_STAR_COUNTS, REGION_GALAXIES, SMGRegions
from worlds.smg.world import SMGWorld


class MissionAccessTests(unittest.TestCase):
    def make_world(self, mode):
        multiworld = setup_multiworld(SMGWorld, seed=120, options={"dome_unlock_mode": mode})
        multiworld.precollected_items[1].clear()
        return multiworld, multiworld.worlds[1]

    def test_every_mission_follows_its_galaxy_without_star_progression(self):
        for mode in (0, 1):
            multiworld, world = self.make_world(mode)
            for parent, galaxies in REGION_GALAXIES.items():
                for galaxy in galaxies:
                    if galaxy in (SMGRegions.GATEWAY_GALAXY, SMGRegions.BOWSERS_GALAXY_REACTOR):
                        continue
                    for galaxy_item, dome_item in ((False, True), (True, False), (True, True)):
                        with self.subTest(mode=mode, galaxy=galaxy, galaxy_item=galaxy_item, dome_item=dome_item):
                            state = CollectionState(multiworld)
                            if galaxy_item:
                                state.collect(world.create_item(f"{galaxy.value} Unlock"))
                            dome_name = f"{parent.value} Unlock"
                            if dome_item and dome_name in world.item_name_to_id:
                                state.collect(world.create_item(dome_name))
                            accessible = galaxy_item and (mode == 0 or dome_item or parent == SMGRegions.COMET_OBSERVATORY)
                            for star in range(1, GALAXY_STAR_COUNTS[galaxy] + 1):
                                self.assertEqual(multiworld.get_location(f"{galaxy.value} {star}", 1).can_reach(state), accessible)

    def test_gateway_tutorial_and_final_boss_keep_their_exceptions(self):
        for mode in (0, 1):
            multiworld, world = self.make_world(mode)
            state = CollectionState(multiworld)
            self.assertTrue(multiworld.get_location("Gateway Galaxy 1", 1).can_reach(state))
            self.assertFalse(multiworld.get_location("Gateway Galaxy 2", 1).can_reach(state))
            state.collect(world.create_item("Gateway Galaxy Unlock"))
            self.assertTrue(multiworld.get_location("Gateway Galaxy 2", 1).can_reach(state))
            state.collect(world.create_item("Bowser's Galaxy Reactor Unlock"))
            boss = multiworld.get_location("Bowser's Galaxy Reactor 1", 1)
            self.assertFalse(boss.can_reach(state))
            for _ in range(world.options.required_stars.value):
                state.collect(world.create_item(ITEM.Star))
            self.assertTrue(boss.can_reach(state))
            self.assertEqual(sum(GALAXY_STAR_COUNTS.values()), 120)


if __name__ == "__main__":
    unittest.main()
