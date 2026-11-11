import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld
from worlds.smg.world import SMGWorld


class PlanetOfTrialsTests(unittest.TestCase):
    def make_world(self, mode):
        multiworld = setup_multiworld(SMGWorld, seed=206, options={"dome_unlock_mode": mode})
        return multiworld, multiworld.worlds[1], CollectionState(multiworld)

    def test_access_matrix_and_independent_destinations(self):
        for mode in (0, 1):
            for items in ((), (206,), (139,), (206, 139), (206, 138, 139, 140)):
                with self.subTest(mode=mode, items=items):
                    multiworld, world, state = self.make_world(mode)
                    names = {206: "Planet of Trials Unlock", 138: "Rolling Gizmo Galaxy Unlock",
                             139: "Bubble Blast Galaxy Unlock", 140: "Loopdeeswoop Galaxy Unlock"}
                    for item in items:
                        state.collect(world.create_item(names[item]))
                    hub = mode == 0 or 206 in items
                    self.assertEqual(multiworld.get_region("Planet of Trials", 1).can_reach(state), hub)
                    for item, region in ((138, "Rolling Gizmo Galaxy"), (139, "Bubble Blast Galaxy"),
                                         (140, "Loopdeeswoop Galaxy")):
                        self.assertEqual(multiworld.get_location(f"{region} 1", 1).can_reach(state), hub and item in items)

    def test_pool_and_slot_mode_agree(self):
        for mode in (0, 1):
            with self.subTest(mode=mode):
                multiworld, world, _ = self.make_world(mode)
                self.assertEqual(sum(item.code == 206 for item in multiworld.itempool), mode)
                self.assertEqual(world.item_name_to_id["Planet of Trials Unlock"], 206)
                self.assertEqual(world.fill_slot_data(), {"required_stars": 3, "dome_unlock_mode": mode,
                                                         "death_link": 0, "death_link_amnesty": 0,
                                                         "death_link_group": "", "hint_price": 100})
                self.assertEqual(len([loc for loc in multiworld.get_locations(1) if loc.address is not None]), 120)

    def test_gateway_tutorial_stays_free(self):
        for mode in (0, 1):
            multiworld, _, state = self.make_world(mode)
            self.assertTrue(multiworld.get_location("Gateway Galaxy 1", 1).can_reach(state))
            self.assertFalse(multiworld.get_location("Gateway Galaxy 2", 1).can_reach(state))


if __name__ == "__main__":
    unittest.main()
