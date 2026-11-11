import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from NetUtils import NetworkItem
from worlds.smg import protocol as p
from worlds.smg.client_state import ProgressStore, StateError
from worlds.smg.dolphin import DolphinBridge
from worlds.smg.hints import HintShop, accessible_locations
from worlds.smg.options import HintPrice
from .test_client import Memory


class HintTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = ProgressStore(Path(temp.name), 'hint-seed', 0, 1, {'required_stars': 3, 'dome_unlock_mode': 1})
        self.store.merge_items([[202, -2, 0, 1], [120, -2, 0, 1]])
        self.store.commit(2)
        self.memory = Memory()
        self.bridge = DolphinBridge(self.memory)
        self.bridge.tick(self.store)
        self.memory.apply_snapshot()
        self.bridge.tick(self.store)
        self.shop = HintShop(self.store)
        self.ctx = SimpleNamespace(bridge=self.bridge, progress=self.store, hint_price=100,
                                   checked_locations=set(), locations_info={}, send_msgs=AsyncMock(),
                                   slot_info={}, player_names={1: 'Mario'},
                                   location_names=Mock(), item_names=Mock())
        self.ctx.location_names.lookup_in_game.return_value = 'Ghostly Galaxy 2'
        self.ctx.item_names.lookup_in_game.return_value = 'Bedroom Unlock'

    def request(self, action=1, cursor=0):
        self.memory.set(p.HINT_REQUEST_OFFSET, self.memory.get(p.HINT_REQUEST_OFFSET) + 1)
        self.memory.set(p.HINT_ACTION_OFFSET, action)
        self.memory.set(p.HINT_CURSOR_OFFSET, cursor)
        self.memory.set(p.HINT_COMMIT_OFFSET, 0)

    async def offer(self):
        self.request()
        await self.shop.tick(self.ctx, True)
        for loc in accessible_locations(self.store):
            self.ctx.locations_info[loc] = NetworkItem(203 if loc == 100049 else 1, loc, 1, int(loc == 100049))
        await self.shop.tick(self.ctx, True)
        self.assertEqual(self.memory.get(p.HINT_STATUS_OFFSET), 1)
        self.assertEqual(self.shop.data['hints'], [])

    def test_yaml_price_roundtrip(self):
        from test.general import setup_multiworld
        from worlds.smg.world import SMGWorld
        for price in (0, 250, 9999):
            world = setup_multiworld(SMGWorld, options={'hint_price': price}).worlds[1]
            self.assertEqual(world.fill_slot_data()['hint_price'], price)

    def test_price_and_accessible_checks(self):
        self.assertEqual(HintPrice.default, 100)
        self.assertEqual(accessible_locations(self.store), {100009, *range(100048, 100054)})
        self.store.record([100049])
        self.assertNotIn(100049, accessible_locations(self.store))

    async def test_purchase_history_restart_and_free_offline_read(self):
        await self.offer()
        self.memory.set(p.HINT_COMMIT_OFFSET, self.memory.get(p.HINT_REQUEST_OFFSET))
        await self.shop.tick(self.ctx, True)
        self.assertEqual(len(self.shop.data['hints']), 1)
        self.assertEqual(self.memory.get(p.HINT_STATUS_OFFSET), 2)
        self.ctx.send_msgs.assert_any_await([{'cmd': 'LocationScouts', 'locations': [100049], 'create_as_hint': 2}])
        # Restart before the game sees the response: replay only that response.
        self.shop = HintShop(self.store)
        await self.shop.tick(self.ctx, False)
        self.assertEqual(len(self.shop.data['hints']), 1)
        self.request(2)
        await self.shop.tick(self.ctx, False)
        self.assertEqual(self.memory.get(p.HINT_STATUS_OFFSET), 2)
        self.assertEqual(self.memory.get(p.HINT_COMMIT_OFFSET), 0)
        self.assertEqual(self.memory.get(p.HINT_ONLINE_OFFSET), 0)

    async def test_unpaid_offer_is_not_free_history_and_disk_failure_does_not_offer(self):
        await self.offer()
        self.request(2)
        await self.shop.tick(self.ctx, True)
        self.assertEqual(self.memory.get(p.HINT_STATUS_OFFSET), 3)
        self.assertEqual(self.shop.data['hints'], [])
        self.request()
        self.shop.save(offer=None)
        with patch('worlds.smg.hints.atomic_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                await self.shop.tick(self.ctx, True)
        self.assertNotEqual(self.memory.get(p.HINT_RESPONSE_OFFSET), self.memory.get(p.HINT_REQUEST_OFFSET))

    async def test_no_hint_offline_or_without_useful_checks(self):
        self.request()
        await self.shop.tick(self.ctx, False)
        self.assertEqual(self.memory.get(p.HINT_STATUS_OFFSET), 3)
        self.request()
        for loc in accessible_locations(self.store):
            self.ctx.locations_info[loc] = NetworkItem(1, loc, 1, 0)
        await self.shop.tick(self.ctx, True)
        self.assertEqual(self.memory.get(p.HINT_STATUS_OFFSET), 3)
        self.assertIsNone(self.shop.data['offer'])

    async def test_corrupt_hint_history_and_epoch_write_protection(self):
        self.shop.path.write_text('{broken')
        with self.assertRaises(StateError): HintShop(self.store)
        await self.offer()
        before = len(self.memory.writes)
        self.memory.set(p.SAVE_EPOCH_OFFSET, 99)
        with self.assertRaises(RuntimeError):
            self.shop.reply(self.bridge, 1, 1, 2, 'stale')
        self.assertEqual(len(self.memory.writes), before)
