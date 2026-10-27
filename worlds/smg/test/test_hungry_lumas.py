import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld
from worlds.smg.world import SMGWorld


GALAXIES = (
    "Sweet Sweet Galaxy", "Sling Pod Galaxy", "Drip Drop Galaxy", "Bigmouth Galaxy",
    "Sand Spiral Galaxy", "Snow Cap Galaxy", "Boo's Boneyard Galaxy",
)


class HungryLumaUnlockTests(unittest.TestCase):
    def test_independent_access_without_domes_or_stars(self):
        for mode in (0, 1):
            multiworld = setup_multiworld(SMGWorld, seed=105, options={"dome_unlock_mode": mode})
            world = multiworld.worlds[1]
            multiworld.precollected_items[1].clear()
            for mask in range(128):
                with self.subTest(mode=mode, mask=mask):
                    state = CollectionState(multiworld)
                    for index, name in enumerate(GALAXIES):
                        self.assertEqual(world.item_name_to_id[f"{name} Unlock"], 100 + index)
                        if mask & (1 << index):
                            state.collect(world.create_item(f"{name} Unlock"))
                    for index, name in enumerate(GALAXIES):
                        self.assertEqual(multiworld.get_location(f"{name} 1", 1).can_reach(state),
                                         bool(mask & (1 << index)))

    def test_hot_collection_does_not_open_other_destinations(self):
        multiworld = setup_multiworld(SMGWorld, seed=105, options={"dome_unlock_mode": 1})
        world = multiworld.worlds[1]
        multiworld.precollected_items[1].clear()
        state = CollectionState(multiworld)
        for index in (5, 0, 6, 3, 2, 1, 4):
            state.collect(world.create_item(f"{GALAXIES[index]} Unlock"))
            for name in GALAXIES:
                self.assertEqual(multiworld.get_location(f"{name} 1", 1).can_reach(state),
                                 state.has(f"{name} Unlock", 1))
            for dome in ("Terrace", "Fountain", "Kitchen", "Bedroom", "Engine Room", "Garden"):
                self.assertFalse(multiworld.get_region(dome, 1).can_reach(state))


if __name__ == "__main__":
    unittest.main()
