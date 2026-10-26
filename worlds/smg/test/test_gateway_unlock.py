import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld
from worlds.smg.world import SMGWorld


class GatewayUnlockTests(unittest.TestCase):
    def test_gateway_and_garden_are_independent(self):
        for mode in (0, 1):
            for gateway in (False, True):
                for garden in (False, True):
                    with self.subTest(mode=mode, gateway=gateway, garden=garden):
                        multiworld = setup_multiworld(SMGWorld, seed=108, options={"dome_unlock_mode": mode})
                        world = multiworld.worlds[1]
                        state = CollectionState(multiworld)
                        if gateway:
                            state.collect(world.create_item("Gateway Galaxy Unlock"))
                        if garden:
                            state.collect(world.create_item("Garden Unlock"))
                        self.assertTrue(multiworld.get_location("Gateway Galaxy 1", 1).can_reach(state))
                        self.assertEqual(multiworld.get_location("Gateway Galaxy 2", 1).can_reach(state), gateway)
                        self.assertEqual(multiworld.get_region("Garden", 1).can_reach(state), mode == 0 or garden)
                        self.assertEqual(world.item_name_to_id["Gateway Galaxy Unlock"], 108)
                        self.assertEqual(sum(item.code == 108 for item in multiworld.itempool), 1)


if __name__ == "__main__":
    unittest.main()
