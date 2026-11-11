import asyncio
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock

from CommonClient import process_server_cmd
from test.general import setup_multiworld
from worlds.smg import protocol as p
from worlds.smg.client import SMGContext
from worlds.smg.client_state import StateError
from worlds.smg.world import SMGWorld
from .test_client import Memory


class DeathLinkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.memory = Memory()
        self.ctx = SMGContext(state_dir=Path(temporary.name), memory=self.memory)
        self.addAsyncCleanup(self.ctx.shutdown)
        self.ctx.server = Mock()
        self.ctx.server.socket.closed = False
        self.ctx.server.socket.close = AsyncMock()
        self.ctx.team, self.ctx.slot = 0, 1
        self.ctx.server_seed_name = 'deathlink-seed'
        self.ctx.player_names[1] = 'MarioNetwork'
        self.ctx.send_msgs = AsyncMock()
        self.ctx.on_package('Connected', {'slot_data': {'required_stars': 6, 'dome_unlock_mode': 0, 'death_link': 1}})
        self.ctx.history_ready = True
        await self.ctx.sync_once()
        self.memory.apply_snapshot()
        await self.ctx.sync_once()
        self.ctx.send_msgs.reset_mock()

    def bounces(self):
        return [packet for call in self.ctx.send_msgs.call_args_list for packet in call.args[0]
                if packet['cmd'] == 'Bounce']

    async def receive(self, time=100, source='OtherPlayer', tags=None, **extra):
        await process_server_cmd(self.ctx, {'cmd': 'Bounced', 'tags': ['DeathLink'] if tags is None else tags,
                                           'data': {'time': time, 'source': source, **extra}})

    async def test_local_death_sent_once_and_own_echo_ignored(self):
        self.memory.set(p.DEATH_LINK_DEATHS_OFFSET, 1)
        await self.ctx.sync_once()
        await self.ctx.sync_once()
        packet, = self.bounces()
        self.assertEqual(packet['tags'], ['DeathLink'])
        self.assertEqual(packet['data']['source'], 'MarioNetwork')
        self.assertIn('MarioNetwork', packet['data']['cause'])
        await self.receive(packet['data']['time'], 'MarioNetwork')
        await self.ctx.sync_once()
        self.assertEqual(self.memory.get(p.DEATH_LINK_REQUEST_OFFSET), 0)
        await self.receive(packet['data']['time'] + 1)
        self.ctx.deathlink_pending = None
        await self.receive(packet['data']['time'], 'MarioNetwork')
        self.assertIsNone(self.ctx.deathlink_pending)

    async def test_remote_receipt_deduplication_and_coalescing(self):
        await self.receive()
        await self.ctx.sync_once()
        self.assertEqual(self.memory.get(p.DEATH_LINK_EPOCH_OFFSET), 1)
        self.assertEqual(self.memory.get(p.DEATH_LINK_REQUEST_OFFSET), 1)
        # Another remote death while the request is pending is coalesced.
        await self.receive(101)
        await self.ctx.sync_once()
        self.assertEqual(self.memory.get(p.DEATH_LINK_REQUEST_OFFSET), 1)
        self.memory.set(p.DEATH_LINK_RESPONSE_OFFSET, 1)
        await self.receive(100)  # Non-adjacent duplicate must not kill another life.
        await self.ctx.sync_once()
        self.assertEqual(self.memory.get(p.DEATH_LINK_REQUEST_OFFSET), 1)
        self.assertEqual(self.bounces(), [])
        self.assertEqual(self.ctx.progress.data['items'], [])
        # A later independent local death still propagates.
        self.memory.set(p.DEATH_LINK_DEATHS_OFFSET, 1)
        await self.ctx.sync_once()
        self.assertEqual(len(self.bounces()), 1)

    async def test_disconnect_cancels_remote_request_and_does_not_replay_offline_death(self):
        await self.receive()
        await self.ctx.sync_once()
        server = self.ctx.server
        self.ctx.server = None
        self.memory.set(p.DEATH_LINK_DEATHS_OFFSET, 1)
        await self.ctx.sync_once()
        self.assertEqual(self.memory.get(p.DEATH_LINK_EPOCH_OFFSET), 0)
        self.ctx.server = server
        await self.ctx.sync_once()
        self.assertEqual(self.bounces(), [])
        self.memory.set(p.DEATH_LINK_DEATHS_OFFSET, 2)
        await self.ctx.sync_once()
        self.assertEqual(len(self.bounces()), 1)

    async def test_toggle_overrides_legacy_seed_and_cancels_pending_death(self):
        processor = self.ctx.command_processor(self.ctx)
        await self.receive()
        self.assertTrue(processor('/deathlink off'))
        await self.ctx.sync_once()
        self.assertNotIn('DeathLink', self.ctx.tags)
        self.assertEqual(self.memory.get(p.DEATH_LINK_REQUEST_OFFSET), 0)
        await self.receive(102)
        self.assertIsNone(self.ctx.deathlink_pending)
        self.assertFalse(processor('/deathlink invalid'))
        self.assertTrue(processor('/deathlink on'))
        self.ctx.on_package('Connected', {'slot_data': {'required_stars': 6, 'dome_unlock_mode': 0}})
        self.assertTrue(self.ctx.deathlink_enabled)
        self.ctx.history_ready = True
        await self.ctx.sync_once()
        self.assertIn('DeathLink', self.ctx.tags)
        # A client reconnect must baseline past deaths instead of replaying them.
        self.assertEqual(self.bounces(), [])

    async def test_wrong_file_and_game_owned_fields_are_protected(self):
        self.ctx.deathlink_pending = ('another file',)
        await self.ctx.sync_once()
        self.assertEqual(self.memory.get(p.DEATH_LINK_REQUEST_OFFSET), 0)
        for offset in (p.DEATH_LINK_DEATHS_OFFSET, p.DEATH_LINK_RESPONSE_OFFSET):
            with self.assertRaises(StateError):
                self.ctx.bridge.word(offset, 1)
        self.memory.set(p.SAVE_SLOT_OFFSET, 0)
        await self.receive()
        await self.ctx.sync_once()
        self.assertEqual(self.memory.get(p.DEATH_LINK_REQUEST_OFFSET), 0)

    async def test_malformed_deaths_are_ignored(self):
        for data in (None, {}, {'time': math.nan, 'source': 'Other'}, {'time': True, 'source': 'Other'},
                     {'time': 123, 'source': []}, {'time': 123, 'source': 'Other', 'cause': []}):
            self.ctx.on_deathlink(data)
        self.assertIsNone(self.ctx.deathlink_pending)

    async def test_ingame_message_resolves_player_game_and_publishes_before_death(self):
        from NetUtils import NetworkSlot, SlotType
        self.ctx.slot_info[2] = NetworkSlot('Alice', 'Celeste', SlotType.player)
        self.ctx.player_names[2] = 'AliceAlias'
        await self.receive(source='AliceAlias')
        self.assertEqual(self.ctx.deathlink_pending_text, 'DeathLink\nAliceAlias died in Celeste.')
        self.memory.writes.clear()
        await self.ctx.sync_once()
        raw = self.memory.read_bytes(self.memory.mailbox + p.DEATH_LINK_TEXT_OFFSET, p.DEATH_LINK_TEXT_UNITS * 2)
        self.assertEqual(raw.decode('utf-16-be').split('\0', 1)[0], 'DeathLink\nAliceAlias died in Celeste.')
        offsets = [address - self.memory.mailbox for address, _ in self.memory.writes]
        self.assertLess(offsets.index(p.DEATH_LINK_TEXT_OFFSET), offsets.index(p.DEATH_LINK_REQUEST_OFFSET))
        self.assertIsNone(self.ctx.deathlink_pending_text)
        self.assertEqual(self.bounces(), [])

    async def test_ingame_message_handles_original_names_unknown_sources_and_ambiguity(self):
        from NetUtils import NetworkSlot, SlotType
        self.ctx.slot_info[2] = NetworkSlot('Alice', 'Celeste', SlotType.player)
        self.ctx.player_names[2] = 'AliceAlias'
        self.assertEqual(self.ctx.deathlink_message('Alice'), 'DeathLink\nAlice died in Celeste.')
        self.assertEqual(self.ctx.deathlink_message('InGameNickname'), 'DeathLink\nInGameNickname died.')
        self.ctx.slot_info[3] = NetworkSlot('Alice', 'PEAK', SlotType.player)
        self.assertEqual(self.ctx.deathlink_message('Alice'), 'DeathLink\nAlice died.')

    async def test_ingame_message_preserves_celeste_cause_in_published_text(self):
        cause = "CelesteDeathLink couldn't climb the mountain."
        await self.receive(source='CelesteDeathLink', cause=cause)
        message = self.ctx.deathlink_pending_text
        self.assertEqual(message.splitlines()[0], 'DeathLink')
        self.assertEqual(' '.join(message.splitlines()[1:]), cause)
        await self.ctx.sync_once()
        raw = self.memory.read_bytes(self.memory.mailbox + p.DEATH_LINK_TEXT_OFFSET, p.DEATH_LINK_TEXT_UNITS * 2)
        self.assertEqual(raw.decode('utf-16-be').split('\0', 1)[0], message)

    async def test_ingame_message_blank_cause_fallback_and_long_cause_layout(self):
        from NetUtils import NetworkSlot, SlotType
        self.ctx.slot_info[2] = NetworkSlot('Alice', 'Celeste', SlotType.player)
        for cause in ('', ' \n\t ', '\x1A'):
            self.assertEqual(self.ctx.deathlink_message('Alice', cause), 'DeathLink\nAlice died in Celeste.')
        cause = 'Alice fell into spikes. ' * 100
        message = self.ctx.deathlink_message('Alice', cause)
        self.assertTrue(message.endswith('...'))
        self.assertLess(len(message), p.DEATH_LINK_TEXT_UNITS)
        self.assertLessEqual(len(message.splitlines()), 3)
        self.assertTrue(all(len(line) <= 34 for line in message.splitlines()))

    async def test_ingame_message_bounds_unicode_and_message_control_sanitization(self):
        from NetUtils import NetworkSlot, SlotType
        source = 'Éléonore\x1A\n' + 'a' * 100
        self.ctx.slot_info[2] = NetworkSlot(source, 'Jeu très long ' * 20, SlotType.player)
        message = self.ctx.deathlink_message(source)
        self.assertEqual(len(message.splitlines()), 3)
        self.assertNotIn('\x1A', message)
        self.assertLess(len(message), p.DEATH_LINK_TEXT_UNITS)
        self.assertIn('Éléonore', message)
        self.assertTrue(message.endswith('...'))
        self.ctx.bridge.sync_deathlink(self.ctx.progress, True, self.ctx.bridge.binding,
                                       'x' * 100 + '\x1A😀')
        raw = self.memory.read_bytes(self.memory.mailbox + p.DEATH_LINK_TEXT_OFFSET, p.DEATH_LINK_TEXT_UNITS * 2)
        self.assertEqual(len(raw), p.DEATH_LINK_TEXT_UNITS * 2)
        self.assertEqual(raw[-2:], b'\0\0')
        self.assertEqual(raw.decode('utf-16-be').split('\0', 1)[0], 'x' * (p.DEATH_LINK_TEXT_UNITS - 1))
        self.memory.set(p.DEATH_LINK_RESPONSE_OFFSET, self.memory.get(p.DEATH_LINK_REQUEST_OFFSET))
        self.ctx.bridge.sync_deathlink(self.ctx.progress, True, self.ctx.bridge.binding, 'A\x1AB😀')
        raw = self.memory.read_bytes(self.memory.mailbox + p.DEATH_LINK_TEXT_OFFSET, p.DEATH_LINK_TEXT_UNITS * 2)
        self.assertEqual(raw.decode('utf-16-be').split('\0', 1)[0], 'A?B?')
        with self.assertRaises(StateError):
            self.ctx.bridge.write(p.DEATH_LINK_TEXT_OFFSET, bytes(p.DEATH_LINK_TEXT_UNITS * 2 + 2))

    async def test_amnesty_cycles_send_every_nth_local_death(self):
        count = 0
        for amnesty in (0, 1, 2, 30):
            with self.subTest(amnesty=amnesty):
                self.ctx.set_deathlink_amnesty(amnesty)
                self.ctx.send_msgs.reset_mock()
                threshold = max(1, amnesty)
                for death in range(1, 2 * threshold + 1):
                    count += 1
                    self.memory.set(p.DEATH_LINK_DEATHS_OFFSET, count)
                    await self.ctx.sync_once()
                    self.assertEqual(len(self.bounces()), death // threshold)
                    self.assertEqual(self.ctx.deathlink_deaths, death % threshold)
                self.assertEqual(self.ctx.deathlink_deaths, 0)

    async def test_amnesty_message_then_only_standard_deathlink_message(self):
        self.ctx.set_deathlink_amnesty(2)
        self.memory.set(p.DEATH_LINK_DEATHS_OFFSET, 1)
        with self.assertLogs('Client', level='INFO') as spared:
            await self.ctx.sync_once()
        self.assertEqual([record.getMessage() for record in spared.records], ['DeathLink Amnesty 1/2'])
        self.assertEqual(self.bounces(), [])
        self.memory.set(p.DEATH_LINK_DEATHS_OFFSET, 2)
        with self.assertLogs('Client', level='INFO') as sent:
            await self.ctx.sync_once()
        self.assertEqual([record.getMessage() for record in sent.records],
                         ['DeathLink: Sending death to your friends...'])
        self.assertEqual(len(self.bounces()), 1)
        self.assertEqual(self.ctx.deathlink_deaths, 0)

    async def test_received_death_does_not_consume_or_reset_amnesty(self):
        self.ctx.set_deathlink_amnesty(2)
        self.memory.set(p.DEATH_LINK_DEATHS_OFFSET, 1)
        await self.ctx.sync_once()
        self.assertEqual(self.ctx.deathlink_deaths, 1)
        await self.receive()
        await self.ctx.sync_once()
        self.assertEqual(self.memory.get(p.DEATH_LINK_REQUEST_OFFSET), 1)
        self.memory.set(p.DEATH_LINK_RESPONSE_OFFSET, 1)
        await self.ctx.sync_once()
        self.assertEqual(self.ctx.deathlink_deaths, 1)
        self.assertEqual(self.bounces(), [])
        self.memory.set(p.DEATH_LINK_DEATHS_OFFSET, 2)
        await self.ctx.sync_once()
        self.assertEqual(len(self.bounces()), 1)
        self.assertEqual(self.ctx.deathlink_deaths, 0)

    async def test_amnesty_seed_setting_reconnect_and_runtime_override(self):
        connected = {'slot_data': {'required_stars': 6, 'dome_unlock_mode': 0, 'death_link': 1,
                                   'death_link_amnesty': 2}}
        self.ctx.on_package('Connected', connected)
        self.assertEqual(self.ctx.deathlink_amnesty, 2)
        self.ctx.history_ready = True
        await self.ctx.sync_once()  # Baseline after reconnect.
        self.memory.set(p.DEATH_LINK_DEATHS_OFFSET, 1)
        await self.ctx.sync_once()
        self.assertEqual(self.ctx.deathlink_deaths, 1)
        self.ctx.on_package('Connected', connected)
        self.assertEqual(self.ctx.deathlink_deaths, 1)
        processor = self.ctx.command_processor(self.ctx)
        self.assertTrue(processor('/deathlink_amnesty'))
        self.assertEqual(self.ctx.deathlink_deaths, 1)
        self.assertTrue(processor('/deathlink_amnesty 3'))
        self.assertEqual(self.ctx.deathlink_deaths, 0)
        self.ctx.on_package('Connected', connected)
        self.assertEqual(self.ctx.deathlink_amnesty, 3)
        for invalid in ('-1', '31', 'hello', '1.5'):
            self.assertFalse(processor(f'/deathlink_amnesty {invalid}'))
            self.assertEqual(self.ctx.deathlink_amnesty, 3)
        self.ctx.deathlink_deaths = 2
        processor('/deathlink off')
        self.assertEqual(self.ctx.deathlink_deaths, 0)

    async def test_legacy_seed_defaults_to_no_amnesty(self):
        self.ctx.on_package('Connected', {'slot_data': {'required_stars': 6, 'dome_unlock_mode': 0}})
        self.assertEqual(self.ctx.deathlink_amnesty, 0)
        self.assertIsNone(self.ctx.client_error)
        for invalid in (-1, 31, True, '2'):
            self.ctx.on_package('Connected', {'slot_data': {'required_stars': 6, 'dome_unlock_mode': 0,
                                                           'death_link_amnesty': invalid}})
            self.assertIsNotNone(self.ctx.client_error)

    async def test_group_receives_only_matching_tags(self):
        self.ctx.set_deathlink_group('amis')
        await self.ctx.sync_once()
        for tag in ('DeathLink', 'DeathLinkautre', 'DeathLinkAmis', 'OtherTag'):
            await self.receive(tags=[tag])
            self.assertIsNone(self.ctx.deathlink_pending)
        await self.receive(tags=['DeathLinkamis'])
        await self.ctx.sync_once()
        self.assertEqual(self.memory.get(p.DEATH_LINK_REQUEST_OFFSET), 1)
        self.assertEqual(self.bounces(), [])

    async def test_independent_peer_packet_variants_and_group_isolation(self):
        # Wire shapes checked against the producers' sources, not executed peers:
        # PEAK: Mickemoose/peak-archipelago, PeakArchipelagoPlugin.cs,
        #       SendDeathLink / OnGroupedDeathLinkPacket / SendUpdatedLinkTags.
        # GodotAP in BK-Simulator/BK-Simulator:
        #       godot_ap/ap_files/connection_info.gd::send_deathlink,
        #       godot_ap/autoloads/archipelago.gd::get_deathlink_tag / Bounced.
        # DELTARUNE: Tenebrosful/DeltaruneAP-mod, code/common/GlobalScript/
        #       gml_GlobalScript_AP_handle_package_functions.gml::AP_async_handle_bounced.
        peers = (
            ('PEAK', {'time': 1794140000.125, 'source': 'Climber', 'cause': 'Climber fell.'}),
            ('GodotAP', {'time': 1794140001.25, 'source': 'GodotPlayer'}),  # cause is optional
            ('DELTARUNE', {'time': 1794140002.5, 'source': 'Kris', 'cause': '', 'uuid': 'peer-uuid'}),
        )
        self.ctx.set_deathlink_group('amis')
        await self.ctx.sync_once()
        for index, (peer, data) in enumerate(peers, 1):
            with self.subTest(peer=peer):
                for wrong_tag in ('DeathLink', 'DeathLinkautre', 'DeathLinkAmis'):
                    await process_server_cmd(self.ctx, {'cmd': 'Bounced', 'tags': [wrong_tag], 'data': data})
                    self.assertIsNone(self.ctx.deathlink_pending)
                await process_server_cmd(self.ctx, {'cmd': 'Bounced', 'tags': ['DeathLinkamis'], 'data': data})
                await self.ctx.sync_once()
                self.assertEqual(self.memory.get(p.DEATH_LINK_REQUEST_OFFSET), index)
                self.memory.set(p.DEATH_LINK_RESPONSE_OFFSET, index)
                await self.ctx.sync_once()
                self.assertEqual(self.bounces(), [])
        # The extra fields and optional cause never become persisted items.
        self.assertEqual(self.ctx.progress.data['items'], [])

    async def test_group_subscriptions_send_and_disable(self):
        self.ctx.tags.add('OtherFeature')
        self.ctx.set_deathlink_group('amis')
        await self.ctx.sync_once()
        self.assertEqual(self.ctx.tags & {'DeathLink', 'DeathLinkamis'}, {'DeathLinkamis'})
        self.memory.set(p.DEATH_LINK_DEATHS_OFFSET, 1)
        await self.ctx.sync_once()
        bounce, = self.bounces()
        self.assertEqual(bounce['tags'], ['DeathLinkamis'])
        # Exercise the actual AP server's routing with the emitted wire packet.
        from MultiServer import BounceTarget
        from types import SimpleNamespace
        same_a = SimpleNamespace(team=0, tags={'DeathLinkamis'})
        same_b = SimpleNamespace(team=0, tags={'AP', 'DeathLinkamis'})
        other = SimpleNamespace(team=0, tags={'DeathLinkautre'})
        standard = SimpleNamespace(team=0, tags={'DeathLink'})
        different_team = SimpleNamespace(team=1, tags={'DeathLinkamis'})
        target = BounceTarget({0}, None, set(bounce['tags']), None)
        self.assertEqual(list(target.match_clients_legacy([same_a, same_b, other, standard, different_team])),
                         [same_a, same_b])
        await self.receive(bounce['data']['time'], 'MarioNetwork', tags=['DeathLinkamis'])
        self.assertIsNone(self.ctx.deathlink_pending)
        self.ctx.command_processor(self.ctx)('/deathlink off')
        await self.ctx.sync_once()
        self.assertNotIn('DeathLinkamis', self.ctx.tags)
        self.assertNotIn('DeathLink', self.ctx.tags)
        self.assertIn('OtherFeature', self.ctx.tags)
        await self.receive(200, tags=['DeathLinkamis'])
        self.assertIsNone(self.ctx.deathlink_pending)

    async def test_group_change_cancels_old_request_before_delivering_new_group(self):
        await self.receive()
        await self.ctx.sync_once()
        self.assertEqual(self.memory.get(p.DEATH_LINK_REQUEST_OFFSET), 1)
        self.ctx.set_deathlink_group('amis')
        await self.receive(101, tags=['DeathLinkamis'])
        await self.ctx.sync_once()
        self.assertEqual(self.memory.get(p.DEATH_LINK_EPOCH_OFFSET), 0)
        self.assertEqual(self.memory.get(p.DEATH_LINK_REQUEST_OFFSET), 1)
        self.assertIsNotNone(self.ctx.deathlink_pending)
        self.memory.set(p.DEATH_LINK_RESPONSE_OFFSET, 1)  # Game acknowledges cancellation.
        await self.ctx.sync_once()
        self.assertEqual(self.memory.get(p.DEATH_LINK_REQUEST_OFFSET), 2)
        self.assertEqual(self.memory.get(p.DEATH_LINK_EPOCH_OFFSET), 1)
        self.assertIsNone(self.ctx.deathlink_pending)

    async def test_group_command_override_reconnect_and_return_to_standard(self):
        connected = {'slot_data': {'required_stars': 6, 'dome_unlock_mode': 0, 'death_link': 1,
                                   'death_link_group': 'seed group'}}
        self.ctx.on_package('Connected', connected)
        self.assertEqual(self.ctx.deathlink_group, 'seed group')
        processor = self.ctx.command_processor(self.ctx)
        self.assertTrue(processor('/deathlink_group "mes amis"'))
        self.assertEqual(self.ctx.deathlink_group, 'mes amis')
        self.ctx.on_package('Connected', connected)
        self.assertEqual(self.ctx.deathlink_group, 'mes amis')
        self.ctx.history_ready = True
        await self.ctx.sync_once()
        self.assertIn('DeathLinkmes amis', self.ctx.tags)
        self.ctx.deathlink_deaths = 1
        self.assertTrue(processor('/deathlink_group'))
        self.assertEqual(self.ctx.deathlink_deaths, 1)  # Query does not change anything.
        self.assertTrue(processor('/deathlink_group ""'))
        await self.ctx.sync_once()
        self.assertEqual(self.ctx.deathlink_group, '')
        self.assertEqual(self.ctx.deathlink_deaths, 0)
        self.assertIn('DeathLink', self.ctx.tags)
        self.assertNotIn('DeathLinkmes amis', self.ctx.tags)
        await self.receive(300, tags=['DeathLinkmes amis'])
        self.assertIsNone(self.ctx.deathlink_pending)
        await self.receive(300)
        self.assertIsNotNone(self.ctx.deathlink_pending)

    async def test_legacy_group_default_and_invalid_groups(self):
        connected = {'slot_data': {'required_stars': 6, 'dome_unlock_mode': 0}}
        self.ctx.on_package('Connected', connected)
        self.assertEqual(self.ctx.deathlink_group, '')
        for invalid in (None, 2, [], 'a\nb', 'a\x00b'):
            with self.assertRaises(StateError):
                self.ctx.set_deathlink_group(invalid)
        self.assertFalse(self.ctx.command_processor(self.ctx)('/deathlink_group "bad\nname"'))
        self.assertEqual(self.ctx.deathlink_group, '')


class DeathLinkOptionTests(unittest.TestCase):
    def test_group_option_export_and_text_validation(self):
        from worlds.smg.options import DeathLinkGroup
        for group in ('', 'amis', 'mes amis', 'Amis', 'équipe 🎮'):
            world = setup_multiworld(SMGWorld, seed=6, options={'death_link_group': group}).worlds[1]
            self.assertEqual(world.fill_slot_data()['death_link_group'], group)
        for group in ('a\nb', 'a\x00b'):
            with self.assertRaises(ValueError):
                DeathLinkGroup.from_any(group)

    def test_seed_option_export(self):
        for enabled in (0, 1):
            world = setup_multiworld(SMGWorld, seed=6, options={'death_link': enabled}).worlds[1]
            self.assertEqual(world.fill_slot_data()['death_link'], enabled)

    def test_amnesty_option_export_and_bounds(self):
        from worlds.smg.options import DeathLinkAmnesty
        for amnesty in (0, 2, 30):
            world = setup_multiworld(SMGWorld, seed=6, options={'death_link_amnesty': amnesty}).worlds[1]
            self.assertEqual(world.fill_slot_data()['death_link_amnesty'], amnesty)
        self.assertEqual(DeathLinkAmnesty.default, 0)
        for invalid in (-1, 31):
            with self.assertRaises(Exception):
                DeathLinkAmnesty.from_any(invalid)


class DeathLinkNetworkTests(unittest.IsolatedAsyncioTestCase):
    async def test_websocket_tag_subscription_remote_death_and_local_bounce(self):
        await self.exercise_group('')

    async def test_websocket_named_group_subscription_remote_death_and_local_bounce(self):
        await self.exercise_group('amis')

    async def exercise_group(self, group):
        import websockets
        from CommonClient import server_loop
        from NetUtils import NetworkPlayer, NetworkSlot, SlotType, decode, encode
        from Utils import version_tuple

        packets, peers = [], []
        tag = 'DeathLink' + group
        subscribed, outgoing = asyncio.Event(), asyncio.Event()

        async def server(socket, path):
            peers.append(socket)
            await socket.send(encode([{'cmd': 'RoomInfo', 'seed_name': 'deathlink-socket', 'version': version_tuple,
                                       'tags': ['AP'], 'password': False, 'hint_cost': 10,
                                       'location_check_points': 1, 'games': ['Super Mario Galaxy']}]))
            async for raw in socket:
                for packet in decode(raw):
                    packets.append(packet)
                    if packet['cmd'] == 'Connect':
                        await socket.send(encode([
                            {'cmd': 'Connected', 'team': 0, 'slot': 1,
                             'slot_info': {1: NetworkSlot('SMGTest', 'Super Mario Galaxy', SlotType.player)},
                             'players': [NetworkPlayer(0, 1, 'SMGTest', 'SMGTest')],
                             'missing_locations': [], 'checked_locations': [],
                             'slot_data': {'required_stars': 3, 'dome_unlock_mode': 0, 'death_link': 1,
                                           'death_link_group': group}},
                            {'cmd': 'ReceivedItems', 'index': 0, 'items': []}]))
                    elif packet['cmd'] == 'ConnectUpdate' and tag in packet['tags']:
                        subscribed.set()
                    elif packet['cmd'] == 'Bounce':
                        outgoing.set()

        async def until(predicate):
            for _ in range(300):
                if predicate():
                    return
                await asyncio.sleep(0.01)
            self.fail('Timed out waiting for a DeathLink network event')

        with tempfile.TemporaryDirectory() as temporary:
            async with websockets.serve(server, '127.0.0.1', 0) as listener:
                memory = Memory()
                ctx = SMGContext(f'ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}',
                                 state_dir=temporary, memory=memory)
                ctx.auth = 'SMGTest'
                ctx.server_task = asyncio.create_task(server_loop(ctx))
                try:
                    await until(lambda: ctx.history_ready)
                    await ctx.sync_once()
                    memory.apply_snapshot()
                    await ctx.sync_once()
                    await asyncio.wait_for(subscribed.wait(), 3)
                    self.assertEqual({value for value in ctx.tags if value.startswith('DeathLink')}, {tag})
                    await peers[0].send(encode([{'cmd': 'Bounced', 'tags': [tag],
                                                'data': {'time': 123, 'source': 'OtherGame',
                                                         'cause': 'OtherGame fell.'}}]))
                    await until(lambda: ctx.deathlink_pending is not None)
                    await ctx.sync_once()
                    self.assertEqual(memory.get(p.DEATH_LINK_REQUEST_OFFSET), 1)
                    memory.set(p.DEATH_LINK_RESPONSE_OFFSET, 1)
                    await ctx.sync_once()
                    self.assertFalse(any(packet['cmd'] == 'Bounce' for packet in packets))
                    memory.set(p.DEATH_LINK_DEATHS_OFFSET, 1)
                    await ctx.sync_once()
                    await asyncio.wait_for(outgoing.wait(), 3)
                    bounce, = [packet for packet in packets if packet['cmd'] == 'Bounce']
                    self.assertEqual(bounce['tags'], [tag])
                    self.assertEqual(bounce['data']['source'], 'SMGTest')
                finally:
                    ctx.exit_event.set()
                    await ctx.shutdown()


if __name__ == '__main__':
    unittest.main()
