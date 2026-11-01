import asyncio
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from worlds.smg import protocol as p
from worlds.smg.client_data import STAGES
from worlds.smg.client_state import (ClientLock, ProgressStore, StateError, check_words, decode_checks,
                                     location_for_star)
from worlds.smg.dolphin import DolphinBridge, DolphinUnavailable, MEM1_START


class Memory:
    """Synthetic MEM1 with controllable game acknowledgements and write failures."""
    descriptor, module, mailbox = 0x80000100, 0x80001000, 0x80002000

    def __init__(self, region='RMGP01'):
        self.data = bytearray(0x1800000)
        self.hooked = True
        self.writes = []
        self.effects = []
        self.region = region
        self.raw_write(MEM1_START, region.encode())
        header = struct.pack('>12I', 0x4150424F, 0x4F543031, 1, 48,
                             int.from_bytes(region[:4].encode(), 'big'), 0x30310000,
                             3, self.module, 0x4000, self.mailbox, p.MAILBOX_SIZE, 0)
        self.raw_write(self.descriptor, header)
        self.raw_write(self.mailbox, struct.pack('>2I', p.MAILBOX_MAGIC, p.MAILBOX_VERSION))
        self.set(p.SAVE_SLOT_OFFSET, 1)
        self.set(p.SAVE_EPOCH_OFFSET, 1)

    def raw_write(self, address, data):
        offset = address - MEM1_START
        self.data[offset:offset + len(data)] = data

    def write_bytes(self, address, data):
        self.writes.append((address, bytes(data)))
        self.raw_write(address, data)

    def read_bytes(self, address, size):
        offset = address - MEM1_START
        return self.data[offset:offset + size]

    def is_hooked(self): return self.hooked
    def hook(self): self.hooked = True
    def un_hook(self): self.hooked = False
    def get(self, offset): return struct.unpack('>I', self.read_bytes(self.mailbox + offset, 4))[0]
    def set(self, offset, value): self.raw_write(self.mailbox + offset, struct.pack('>I', value))

    def apply_snapshot(self):
        raw = bytes(self.read_bytes(self.mailbox + p.SNAPSHOT_OFFSET, 68))
        words = struct.unpack('>17I', raw)
        assert words[0] == self.get(p.SAVE_EPOCH_OFFSET)
        self.raw_write(self.mailbox + p.IDENTITY_OFFSET, struct.pack('>4I', *words[1:5]))
        self.set(p.NEXT_ITEM_INDEX_OFFSET, words[11])
        self.set(p.SYNC_RESPONSE_OFFSET, self.get(p.SYNC_REQUEST_OFFSET))
        self.set(p.SYNC_ERROR_OFFSET, 0)
        return words

    def consume(self):
        read, write = self.get(p.INCOMING_READ_COUNT_OFFSET), self.get(p.INCOMING_WRITE_COUNT_OFFSET)
        assert write != read
        offset = p.INCOMING_EVENTS_OFFSET + read % 32 * 8
        item, index = struct.unpack('>2I', self.read_bytes(self.mailbox + offset, 8))
        assert index == self.get(p.NEXT_ITEM_INDEX_OFFSET)
        if item != p.COMMAND_SKIP_ITEM:
            self.effects.append(item)
        self.set(p.NEXT_ITEM_INDEX_OFFSET, index + 1)
        self.set(p.INCOMING_READ_COUNT_OFFSET, (read + 1) & 0xFFFFFFFF)
        return item

    def star(self, stage, star):
        write = self.get(12)
        raw = stage.encode().ljust(64, b'\0') + struct.pack('>I', star)
        self.raw_write(self.mailbox + 20 + (write % 32) * 68, raw)
        self.set(12, (write + 1) & 0xFFFFFFFF)


class ClientTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def store(self, **kwargs):
        return ProgressStore(self.directory, kwargs.get('seed', 'seed-A'), 0, 1,
                             {'required_stars': 3, 'dome_unlock_mode': 1})

    def bound(self, items=(), region='RMGP01'):
        store, memory = self.store(), Memory(region)
        store.merge_items([[item, 100001 + i, 1, 0] for i, item in enumerate(items)])
        bridge = DolphinBridge(memory)
        bridge.tick(store)
        memory.apply_snapshot()
        return store, memory, bridge

    def test_mapping_and_all_120_bits(self):
        from worlds.smg.locations import LOCATION_NAME_TO_ID
        from worlds.smg.regions import GALAXY_STAR_COUNTS
        expected = list(LOCATION_NAME_TO_ID.values())
        actual = [location_for_star(stage, star) for stage, count in STAGES for star in range(1, count + 1)]
        self.assertEqual(actual, expected)
        self.assertEqual([count for _, count in STAGES], list(GALAXY_STAR_COUNTS.values()))
        self.assertEqual(decode_checks(check_words(actual)), set(expected))
        for stage, star in [('UnknownGalaxy', 1), ('EggStarGalaxy', 7), ('EggStarGalaxy', 0)]:
            with self.assertRaises(StateError):
                location_for_star(stage, star)

    def test_protocol_and_cpp_mapping_match_companion_checkout(self):
        import ast
        import re
        root = Path(__file__).resolve().parents[4] / 'MarioGalaxy-Archipelago-Petari'
        if not root.exists():
            self.skipTest('Companion Petari checkout is unavailable')
        namespace = {}
        exec(compile(ast.parse((root / 'archipelago_protocol.py').read_text()), 'protocol', 'exec'), namespace)
        for key, value in namespace.items():
            if key.isupper():
                self.assertEqual(getattr(p, key), value, key)
        rows = re.findall(r'\{"([^"]+)", (\d+)\}', (root / 'include/Game/Archipelago/ClientLocations.inc').read_text())
        self.assertEqual([(s, int(c)) for s, c in rows], list(STAGES))

    def test_snapshot_restart_and_history_deduplication(self):
        store = self.store()
        items = [[item, 100001 + i, 1, 0] for i, item in enumerate([109, 205, 206, 2, 1, 2])]
        store.merge_items(items)
        store.merge_items(items)
        store.commit(6)
        store.record([100001, 100120], True)
        restored = self.store()
        words = struct.unpack('>17I', restored.snapshot(7))
        self.assertEqual(words[0], 7)
        self.assertEqual(words[7], 2)
        self.assertEqual(words[8:10], (1 << 9, 0))
        self.assertEqual(words[10], (1 << 5) | (1 << 6))
        self.assertEqual(words[11], 6)
        self.assertEqual(decode_checks(words[12:16]), {100001, 100120})
        self.assertEqual(words[16], 1)
        with self.assertRaises(StateError):
            store.merge_items([[2, 9, 1, 0]])

    def test_corrupt_journal_and_wrong_options_fail_closed(self):
        store = self.store()
        store.save()
        store.path.write_text('{broken')
        with self.assertRaises(StateError):
            self.store()
        store.save()
        with self.assertRaises(StateError):
            ProgressStore(self.directory, 'seed-A', 0, 1, {'required_stars': 4, 'dome_unlock_mode': 1})

    def test_exclusive_writer_lock(self):
        lock = ClientLock(self.directory)
        try:
            with self.assertRaises(StateError):
                ClientLock(self.directory)
        finally:
            lock.close()
        ClientLock(self.directory).close()

    def test_wrong_seed_cannot_bind_same_native_file(self):
        self.store().bind('default', 'RMGP01', 1, 0)
        with self.assertRaises(StateError):
            self.store(seed='seed-B').bind('default', 'RMGP01', 1, 0)
        self.store(seed='seed-B').bind('other-user-directory', 'RMGP01', 1, 0)

    def test_progression_restarts_and_client_restarts_do_not_replay_coins(self):
        store, memory, bridge = self.bound([109, 200, 2, 1])
        for item in [109, 200, 2, 1]:
            bridge.tick(store)
            self.assertEqual(memory.consume(), item)
        bridge.tick(store)
        self.assertEqual(store.data['committed'], 4)
        replacement = DolphinBridge(memory)
        replacement.tick(self.store())
        self.assertEqual(memory.effects.count(1), 1)
        restarted = Memory()
        replacement = DolphinBridge(restarted)
        replacement.tick(self.store())
        words = restarted.apply_snapshot()
        self.assertEqual(words[7], 1)
        self.assertEqual(words[8], 1 << 9)
        self.assertEqual(words[10], 1)
        self.assertEqual(words[11], 4)
        replacement.tick(self.store())
        self.assertEqual(restarted.effects, [])

    def test_uncertain_coin_is_skipped_after_publication_failure(self):
        store, memory, bridge = self.bound([1])
        original = memory.write_bytes

        def fail_publish(address, data):
            if address == memory.mailbox + p.INCOMING_WRITE_COUNT_OFFSET:
                raise OSError('simulated process loss before publication')
            original(address, data)

        with patch.object(memory, 'write_bytes', fail_publish), self.assertRaises(OSError):
            bridge.tick(store)
        self.assertEqual(self.store().data['committed'], 1)
        DolphinBridge(memory).tick(self.store())
        self.assertEqual(memory.consume(), p.COMMAND_SKIP_ITEM)
        self.assertEqual(memory.effects, [])

    def test_disk_failure_does_not_ack_checks_or_mutate_journal(self):
        store, memory, bridge = self.bound()
        memory.star('EggStarGalaxy', 1)
        with patch('worlds.smg.client_state.atomic_json', side_effect=OSError('disk full')), self.assertRaises(OSError):
            bridge.tick(store)
        self.assertEqual(memory.get(16), 0)
        self.assertEqual(store.data['checks'], [])
        bridge.tick(store)
        self.assertEqual(memory.get(16), 1)
        self.assertEqual(self.store().data['checks'], [location_for_star('EggStarGalaxy', 1)])

    def test_disk_failure_does_not_reserve_or_deliver_coin(self):
        store, memory, bridge = self.bound([1])
        with patch('worlds.smg.client_state.atomic_json', side_effect=OSError('disk full')), self.assertRaises(OSError):
            bridge.tick(store)
        self.assertEqual(store.data['committed'], 0)
        self.assertEqual(memory.get(p.INCOMING_WRITE_COUNT_OFFSET), 0)

    def test_unknown_events_and_foreign_identity_fail_closed(self):
        store, memory, bridge = self.bound()
        memory.star('UnknownGalaxy', 1)
        with self.assertRaises(StateError):
            bridge.tick(store)
        self.assertEqual(memory.get(16), 0)
        memory.set(12, 0)
        memory.set(p.IDENTITY_OFFSET, 123)
        before = len(memory.writes)
        with self.assertRaises(StateError):
            bridge.tick(store)
        self.assertEqual(len(memory.writes), before)

    def test_rollbacks_restore_progression_from_journal(self):
        store, memory, bridge = self.bound([109, 2])
        for _ in range(2):
            bridge.tick(store)
            memory.consume()
        bridge.tick(store)
        memory.set(p.NEXT_ITEM_INDEX_OFFSET, 0)
        bridge.tick(store)
        words = memory.apply_snapshot()
        self.assertEqual(words[7], 1)
        self.assertEqual(words[11], 2)

    def test_wrong_game_protocol_descriptor_and_write_bounds(self):
        for region in ('RMGP01', 'RMGE01'):
            with self.subTest(region=region):
                store, memory, bridge = self.bound(region=region)
                self.assertEqual(bridge.found['region'], region)
                for offset in (0, p.NEXT_ITEM_INDEX_OFFSET, p.CHECKS_OFFSET, p.GOAL_COMPLETED_OFFSET):
                    with self.assertRaises(StateError):
                        bridge.write(offset, b'\0' * 4)
                memory.set(4, 4)
                with self.assertRaises(DolphinUnavailable):
                    bridge.validate()
                with self.assertRaisesRegex(StateError, 'Incompatible'):
                    bridge.discover()
        memory = Memory()
        memory.raw_write(MEM1_START, b'WRONG!')
        with self.assertRaises(DolphinUnavailable):
            DolphinBridge(memory).discover()

    def test_ambiguous_descriptors_and_stale_file_reject_writes(self):
        memory = Memory()
        memory.raw_write(0x80000200, memory.read_bytes(memory.descriptor, 48))
        with self.assertRaisesRegex(StateError, 'Multiple'):
            DolphinBridge(memory).discover()
        memory = Memory()
        bridge = DolphinBridge(memory)
        bridge.discover()
        with self.assertRaises(DolphinUnavailable):
            bridge.word(p.SYNC_REQUEST_OFFSET, 1, epoch=99)
        self.assertFalse(memory.writes)


class ClientNetworkTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_websocket_handshake_items_checks_and_goal(self):
        import websockets
        from CommonClient import server_loop
        from NetUtils import NetworkItem, NetworkPlayer, NetworkSlot, SlotType, decode, encode
        from Utils import version_tuple
        from worlds.smg.client import SMGContext

        packets = []
        received_goal = asyncio.Event()

        async def server(socket, path):
            await socket.send(encode([{'cmd': 'RoomInfo', 'seed_name': 'socket-seed', 'version': version_tuple,
                                       'tags': ['AP'], 'password': False, 'hint_cost': 10,
                                       'location_check_points': 1, 'games': ['Super Mario Galaxy']}]))
            async for raw in socket:
                for message in decode(raw):
                    packets.append(message)
                    if message['cmd'] == 'Connect':
                        await socket.send(encode([
                            {'cmd': 'Connected', 'team': 0, 'slot': 1,
                             'slot_info': {1: NetworkSlot('SMGTest', 'Super Mario Galaxy', SlotType.player)},
                             'players': [NetworkPlayer(0, 1, 'SMGTest', 'SMGTest')],
                             'missing_locations': [100001], 'checked_locations': [],
                             'slot_data': {'required_stars': 3, 'dome_unlock_mode': 0}},
                            {'cmd': 'ReceivedItems', 'index': 0, 'items': [NetworkItem(2, 100001, 1, 1)]},
                        ]))
                    elif message['cmd'] == 'StatusUpdate' and message['status'] == 30:
                        received_goal.set()

        with tempfile.TemporaryDirectory() as temporary:
            async with websockets.serve(server, '127.0.0.1', 0) as listener:
                port = listener.sockets[0].getsockname()[1]
                memory = Memory()
                ctx = SMGContext(f'ws://127.0.0.1:{port}', state_dir=temporary, memory=memory)
                ctx.auth = 'SMGTest'
                ctx.server_task = asyncio.create_task(server_loop(ctx))
                try:
                    for _ in range(300):
                        if ctx.history_ready:
                            break
                        await asyncio.sleep(0.01)
                    self.assertTrue(ctx.history_ready, 'WebSocket authentication did not complete')
                    self.assertIsNone(ctx.client_error)
                    await ctx.sync_once()
                    memory.apply_snapshot()
                    await ctx.sync_once()
                    self.assertEqual(memory.consume(), 2)
                    memory.star('BeltConveyerExGalaxy', 1)
                    memory.set(p.GOAL_COMPLETED_OFFSET, 1)
                    await ctx.sync_once()
                    await asyncio.wait_for(received_goal.wait(), 3)
                    connect = next(msg for msg in packets if msg['cmd'] == 'Connect')
                    self.assertEqual(connect['game'], 'Super Mario Galaxy')
                    self.assertEqual(connect['items_handling'], 0b111)
                    self.assertIn({'cmd': 'LocationChecks', 'locations': [100001]}, packets)
                finally:
                    ctx.exit_event.set()
                    await ctx.shutdown()

    async def test_commonclient_packets_offline_checks_goal_and_reconnect(self):
        from CommonClient import process_server_cmd
        from NetUtils import NetworkItem
        from worlds.smg.client import SMGContext
        with tempfile.TemporaryDirectory() as temporary:
            memory = Memory()
            ctx = SMGContext(state_dir=temporary, memory=memory)
            sent = []

            async def send(messages): sent.extend(messages)
            ctx.send_msgs = send
            ctx.server_seed_name, ctx.team, ctx.slot = 'network-seed', 0, 1
            ctx.server = object()
            connected = {'slot_data': {'required_stars': 3, 'dome_unlock_mode': 0}}
            ctx.on_package('Connected', connected)
            await process_server_cmd(ctx, {'cmd': 'ReceivedItems', 'index': 0,
                                          'items': [NetworkItem(109, 100001, 1, 1), NetworkItem(2, 100002, 1, 1)]})
            await ctx.sync_once()
            memory.apply_snapshot()
            for _ in range(2):
                await ctx.sync_once()
                memory.consume()
            await ctx.sync_once()
            self.assertEqual(ctx.progress.data['committed'], 2)
            # Repeated full histories and out-of-order packets use CommonClient Sync.
            await process_server_cmd(ctx, {'cmd': 'ReceivedItems', 'index': 0,
                                          'items': [NetworkItem(109, 100001, 1, 1), NetworkItem(2, 100002, 1, 1)]})
            await process_server_cmd(ctx, {'cmd': 'ReceivedItems', 'index': 99, 'items': []})
            self.assertIn({'cmd': 'Sync'}, sent)
            await ctx.sync_once()
            self.assertEqual(memory.effects, [109, 2])
            ctx.server, ctx.slot = None, None
            memory.star('KoopaBattleVs3Galaxy', 1)
            memory.set(p.GOAL_COMPLETED_OFFSET, 1)
            await ctx.sync_once()
            self.assertEqual(memory.get(16), 1)
            self.assertTrue(ctx.progress.data['goal'])
            ctx.server, ctx.slot = object(), 1
            ctx.on_package('Connected', connected)
            await process_server_cmd(ctx, {'cmd': 'ReceivedItems', 'index': 0,
                                          'items': [NetworkItem(109, 100001, 1, 1), NetworkItem(2, 100002, 1, 1)]})
            sent.clear()
            await ctx.sync_once()
            self.assertIn({'cmd': 'LocationChecks', 'locations': [100008]}, sent)
            self.assertTrue(any(msg['cmd'] == 'StatusUpdate' and msg['status'] == 30 for msg in sent))
            sent.clear()
            await ctx.sync_once()
            self.assertEqual(sent, [])


if __name__ == '__main__':
    unittest.main()
