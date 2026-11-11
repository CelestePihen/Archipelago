"""SMG-only hint shop. Offers are durable before the native payment handshake."""
from __future__ import annotations
import json
import struct
import textwrap
from . import protocol as p
from .client_state import StateError, atomic_json
from .items import ITEM_NAME_TO_ID
from .locations import LOCATION_NAME_TO_ID
from .regions import DOMES, REGION_GALAXIES, SMGRegions


def accessible_locations(progress):
    items = {i[0] for i in progress.data['items'][:progress.data['committed']]}
    stars = sum(i[0] == 2 for i in progress.data['items'][:progress.data['committed']])
    result = set()
    for parent, galaxies in REGION_GALAXIES.items():
        if parent in DOMES and progress.data['slot_data']['dome_unlock_mode'] == 1:
            if ITEM_NAME_TO_ID[parent.value + ' Unlock'] not in items:
                continue
        for galaxy in galaxies:
            unlock = ITEM_NAME_TO_ID[galaxy.value + ' Unlock'] in items
            if galaxy != SMGRegions.GATEWAY_GALAXY and not unlock:
                continue
            if galaxy == SMGRegions.BOWSERS_GALAXY_REACTOR and stars < progress.data['slot_data']['required_stars']:
                continue
            for name, location in LOCATION_NAME_TO_ID.items():
                if name.rsplit(' ', 1)[0] != galaxy.value:
                    continue
                if galaxy == SMGRegions.GATEWAY_GALAXY and name.endswith(' 2') and not unlock:
                    continue
                result.add(location)
    return result - set(progress.data['checks'])


class HintShop:
    def __init__(self, progress):
        self.path = progress.path.with_suffix('.hints.json')
        self.data = {'identity': progress.data['identity'], 'hints': [], 'offer': None}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
                if (set(data) != set(self.data) or data['identity'] != self.data['identity']
                        or not isinstance(data['hints'], list)
                        or any(not self.valid_hint(h) for h in data['hints'])
                        or (data['offer'] is not None and not self.valid_hint(data['offer']))):
                    raise ValueError('invalid hint history')
                self.data = data
            except (ValueError, TypeError, KeyError) as exc:
                raise StateError(f'Cannot read hint journal: {exc}') from exc
        self.scouted = set()
        self.heartbeat = 0
        self.binding = None

    @staticmethod
    def valid_hint(h):
        return (isinstance(h, dict) and set(h) == {'location', 'text'}
                and h['location'] in LOCATION_NAME_TO_ID.values()
                and isinstance(h['text'], str) and len(h['text']) <= 220)

    def save(self, **changes):
        data = {**self.data, **changes}
        atomic_json(self.path, data)
        self.data = data

    def reply(self, bridge, epoch, request, status, text=''):
        text = ''.join(c if c == '\n' or c.isprintable() and ord(c) <= 0xffff and not 0xd800 <= ord(c) <= 0xdfff else '?' for c in text)
        raw = text[:p.HINT_TEXT_UNITS - 1].encode('utf-16-be')
        bridge.write(p.HINT_TEXT_OFFSET, raw.ljust(p.HINT_TEXT_UNITS * 2, b'\0'), epoch)
        bridge.word(p.HINT_STATUS_OFFSET, status, epoch)
        bridge.word(p.HINT_RESPONSE_OFFSET, request, epoch)

    async def tick(self, ctx, online):
        bridge, progress = ctx.bridge, ctx.progress
        if not bridge.found:
            return
        state = bridge.state()
        if (not state['slot'] or state['request'] != state['response'] or state['error']
                or tuple(state['identity']) != progress.token):
            return
        epoch = state['epoch']
        if self.binding != bridge.binding:
            bridge.word(p.HINT_RESPONSE_OFFSET, 0, epoch)
            bridge.word(p.HINT_STATUS_OFFSET, 0, epoch)
            self.binding = bridge.binding
        self.heartbeat = (self.heartbeat + 1) & 0xffffffff
        price = ctx.hint_price
        bridge.write(p.HINT_PRICE_OFFSET, struct.pack('>3I', price, self.heartbeat, int(online)), epoch)
        bridge.word(p.HINT_EPOCH_OFFSET, epoch, epoch)
        request, action, cursor, commit = struct.unpack('>4I', bridge.read(bridge.found['address'] + p.HINT_OFFSET, 16))
        if not request:
            return
        offer = self.data['offer']
        if commit == request and offer:
            hints = self.data['hints']
            if not any(h['location'] == offer['location'] for h in hints):
                self.save(hints=hints + [offer])
                if online:
                    await ctx.send_msgs([{'cmd': 'LocationScouts', 'locations': [offer['location']], 'create_as_hint': 2}])
            self.reply(bridge, epoch, request, 2, offer['text'] + '\nA : Indice suivant | B : Retour')
            return
        response, status = struct.unpack('>2I', bridge.read(bridge.found['address'] + p.HINT_RESPONSE_OFFSET, 8))
        if action == 0 or (response == request and status in (2, 3)):
            return
        if action == 2:
            hints = self.data['hints']
            if not hints:
                self.reply(bridge, epoch, request, 3, 'Aucun indice achete.\nB : Retour')
            else:
                index = cursor % len(hints)
                self.reply(bridge, epoch, request, 2, f'Indice {index + 1}/{len(hints)}\n' + hints[index]['text'] + '\nA : Suivant | B : Retour')
            return
        if action != 1:
            raise StateError('Invalid hint action')
        if not online:
            self.reply(bridge, epoch, request, 3, 'Serveur deconnecte.\nB : Retour')
            return
        locations = accessible_locations(progress) - set(ctx.checked_locations)
        locations -= {h['location'] for h in self.data['hints']}
        if offer and offer['location'] not in locations:
            self.save(offer=None)
            offer = None
        if not offer:
            unknown = locations - ctx.locations_info.keys()
            send = unknown - self.scouted
            if send:
                await ctx.send_msgs([{'cmd': 'LocationScouts', 'locations': sorted(send), 'create_as_hint': 0}])
                self.scouted.update(send)
            if unknown:
                return
            useful = [ctx.locations_info[loc] for loc in sorted(locations) if ctx.locations_info[loc].flags & 1]
            if not useful:
                self.reply(bridge, epoch, request, 3, 'Aucun nouvel indice utile dans\ntes galaxies accessibles.\nAucun fragment depense.\nB : Retour')
                return
            item = useful[0]
            location_name = ctx.location_names.lookup_in_game(item.location, 'Super Mario Galaxy')
            game = ctx.slot_info[item.player].game if item.player in ctx.slot_info else 'Super Mario Galaxy'
            item_name = ctx.item_names.lookup_in_game(item.item, game)
            owner = ctx.player_names.get(item.player, str(item.player))
            text = '\n'.join(textwrap.wrap(f'{location_name} : {item_name} ({owner})', width=34, max_lines=5, placeholder='...'))
            offer = {'location': item.location, 'text': text}
            self.save(offer=offer)
        # Publishing an offer does not grant a free history entry. Only the
        # game's commit after deducting Star Bits adds it to purchased hints.
        self.reply(bridge, epoch, request, 1)
