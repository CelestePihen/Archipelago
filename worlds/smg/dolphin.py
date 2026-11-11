"""Validated mailbox transport. All writes are confined to client-owned fields."""
from __future__ import annotations

import struct

from . import protocol as p
from .client_state import StateError, decode_checks, location_for_star

MEM1_START, MEM1_END = 0x80000000, 0x81800000


class DolphinUnavailable(RuntimeError):
    pass


class DolphinBridge:
    def __init__(self, memory, profile='default'):
        self.memory = memory
        self.profile = profile
        self.found = None
        self.binding = None
        self.deathlink_state = None
        self.deathlink_request_pending = False

    def forget(self):
        self.found = self.binding = None
        self.deathlink_state = None
        self.deathlink_request_pending = False

    def read(self, address, size):
        if size < 0 or not MEM1_START <= address <= MEM1_END or size > MEM1_END - address:
            raise StateError('Read outside Wii MEM1')
        data = bytes(self.memory.read_bytes(address, size))
        if len(data) != size:
            raise DolphinUnavailable('Short Dolphin memory read')
        return data

    def discover(self):
        if not self.memory.is_hooked():
            self.memory.hook()
        if not self.memory.is_hooked():
            raise DolphinUnavailable('Waiting for Dolphin and a running SMG game')
        region = self.read(MEM1_START, 6).decode('ascii', errors='replace')
        if region not in ('RMGP01', 'RMGE01'):
            raise DolphinUnavailable('Waiting for Super Mario Galaxy PAL or USA')
        data = self.read(MEM1_START, MEM1_END - MEM1_START)
        found = []
        start = 0
        old_protocol = False
        while (offset := data.find(b'APBOOT01', start)) >= 0:
            start = offset + 8
            if offset % 4 or offset + 48 > len(data):
                continue
            header = data[offset:offset + 48]
            words = struct.unpack('>12I', header)
            _, _, version, size, r0, r1, status, module, length, mailbox, mailbox_size, error = words
            if (version, size, r0, r1) != (1, 48, int.from_bytes(region[:4].encode(), 'big'), 0x30310000):
                continue
            if status == 4:
                raise StateError(f'SMG bootstrap rejected the module (error {error})')
            if (status != 3 or module % 32 or not MEM1_START <= module < MEM1_END
                    or not 0 < length <= MEM1_END - module or mailbox % 4
                    or not module <= mailbox <= module + length - mailbox_size or mailbox_size < 12):
                continue
            magic, protocol = struct.unpack_from('>2I', data, mailbox - MEM1_START)
            if magic == p.MAILBOX_MAGIC and (protocol != p.MAILBOX_VERSION or mailbox_size != p.MAILBOX_SIZE):
                old_protocol = True
            if magic == p.MAILBOX_MAGIC and protocol == p.MAILBOX_VERSION and mailbox_size == p.MAILBOX_SIZE:
                found.append({'descriptor': MEM1_START + offset, 'header': header, 'address': mailbox, 'region': region})
        if len(found) > 1:
            raise StateError('Multiple SMG mailboxes; refusing ambiguous writes')
        if not found:
            if old_protocol:
                raise StateError('Incompatible SMG mailbox. Rebuild the PAL/USA module and restart Dolphin (v7 required).')
            raise DolphinUnavailable('Waiting for the SMG Archipelago module to finish loading')
        self.found = found[0]
        self.validate()

    def validate(self):
        found = self.found
        if not found:
            raise DolphinUnavailable('No SMG mailbox')
        if (self.read(MEM1_START, 6) != found['region'].encode()
                or self.read(found['descriptor'], 48) != found['header']
                or self.read(found['address'], 8) != struct.pack('>2I', p.MAILBOX_MAGIC, p.MAILBOX_VERSION)):
            self.forget()
            raise DolphinUnavailable('SMG restarted or changed its module; rediscovering')

    def state(self):
        self.validate()
        address = self.found['address']
        raw = self.read(address + p.SYNC_OFFSET, 60)
        values = struct.unpack('>15I', raw)
        request, response, slot, character, epoch, index, error = values[:7]
        if self.read(address + p.SAVE_SLOT_OFFSET, 12) != raw[8:20]:
            raise DolphinUnavailable('Save file changed during mailbox read')
        if slot > 6 or character > 1 or error > 3:
            raise StateError('Invalid SMG save metadata')
        goal = struct.unpack('>I', self.read(address + p.GOAL_COMPLETED_OFFSET, 4))[0]
        if goal > 1:
            raise StateError('Invalid SMG goal state')
        return dict(request=request, response=response, slot=slot, character=character, epoch=epoch,
                    index=index, error=error, checks=decode_checks(values[7:11]), identity=values[11:15], goal=bool(goal))

    def write(self, offset, data, epoch=None):
        # No game-owned progression, flags or arbitrary game addresses may be written.
        allowed = ((p.SYNC_REQUEST_OFFSET, 4), (p.SNAPSHOT_OFFSET, 68),
                   (p.INCOMING_WRITE_COUNT_OFFSET, 4), (p.INCOMING_EVENTS_OFFSET, p.EVENT_CAPACITY * 8),
                   (16, 4), (p.DEATH_LINK_EPOCH_OFFSET, 8), (p.DEATH_LINK_TEXT_OFFSET, p.DEATH_LINK_TEXT_UNITS * 2))
        if not any(start <= offset and offset + len(data) <= start + size for start, size in allowed):
            raise StateError('Attempted write outside client-owned mailbox fields')
        self.validate()
        base = self.found['address']
        if epoch is not None and struct.unpack('>I', self.read(base + p.SAVE_EPOCH_OFFSET, 4))[0] != epoch:
            raise DolphinUnavailable('Save changed before mailbox write')
        self.memory.write_bytes(base + offset, data)
        if self.read(base + offset, len(data)) != data:
            raise DolphinUnavailable('Mailbox write verification failed')

    def word(self, offset, value, epoch=None):
        self.write(offset, struct.pack('>I', value & 0xFFFFFFFF), epoch)

    def queue_counts(self):
        write, read = struct.unpack('>2I', self.read(self.found['address'] + p.INCOMING_QUEUE_OFFSET, 8))
        if (write - read) & 0xFFFFFFFF > p.EVENT_CAPACITY:
            raise StateError('Corrupt incoming SMG queue')
        return write, read

    def enqueue(self, item, index, epoch):
        write, read = self.queue_counts()
        if (write - read) & 0xFFFFFFFF >= p.EVENT_CAPACITY:
            return False
        offset = p.INCOMING_EVENTS_OFFSET + (write % p.EVENT_CAPACITY) * 8
        self.write(offset, struct.pack('>2I', item, index), epoch)
        # Publish only after all payload bytes have been written and read back.
        self.word(p.INCOMING_WRITE_COUNT_OFFSET, write + 1, epoch)
        return True

    def collect(self, store, state):
        base = self.found['address']
        write, read = struct.unpack('>2I', self.read(base + 12, 8))
        count = (write - read) & 0xFFFFFFFF
        if count > p.EVENT_CAPACITY:
            raise StateError('Corrupt outgoing SMG queue')
        checks = set(state['checks'])
        for sequence in range(read, read + count):
            event = self.read(base + 20 + (sequence % p.EVENT_CAPACITY) * p.EVENT_SIZE, p.EVENT_SIZE)
            stage = event[:64].split(b'\0', 1)[0].decode('ascii')
            star = struct.unpack_from('>I', event, 64)[0]
            checks.add(location_for_star(stage, star))
        # Disk durability precedes queue acknowledgement and all network sends.
        store.record(checks, state['goal'])
        if count:
            if self.read(base + 16, 4) != struct.pack('>I', read):
                raise StateError('Another client consumed the SMG star queue')
            self.word(16, write, state['epoch'])

    def tick(self, store):
        if not self.found:
            self.discover()
        state = self.state()
        if state['request'] == 0 and state['slot'] == 0:
            # Opt into v5 file tracking. The zero snapshot is a probe, never a restore.
            self.word(p.SYNC_REQUEST_OFFSET, 1)
            return 'Waiting for a loaded save file'
        if not state['slot']:
            return 'Waiting for a loaded save file'
        binding = (self.found['region'], state['slot'], state['character'], state['epoch'], store.token)
        if self.binding != binding:
            store.bind(self.profile, self.found['region'], state['slot'], state['character'])
            self.binding = binding
        identity = tuple(state['identity'])
        if any(identity) and identity != store.token:
            raise StateError('Running SMG file is bound to a different Archipelago seed/slot')
        self.collect(store, state)
        if state['request'] != state['response']:
            return 'Restoring Archipelago progress'
        if state['error'] in (2, 3):
            raise StateError(f'SMG rejected the restore snapshot (error {state["error"]})')
        committed = store.data['committed']
        # Rewind of progression (e.g. a savestate) restores the journal snapshot.
        gap = store.data['items'][state['index']:committed]
        needs_restore = identity != store.token or state['error'] or any(item[0] != 1 for item in gap)
        if needs_restore:
            snapshot = store.snapshot(state['epoch'])
            self.write(p.SNAPSHOT_OFFSET, snapshot, state['epoch'])
            self.word(p.SYNC_REQUEST_OFFSET, ((state['request'] + 1) & 0xFFFFFFFF) or 1, state['epoch'])
            return 'Restoring Archipelago progress'
        if state['index'] > len(store.data['items']):
            raise StateError('Game item cursor is ahead of the cached server history')
        if state['index'] > committed:
            store.commit(state['index'])
            committed = state['index']
        write, read = self.queue_counts()
        if write == read:
            index = state['index']
            if index < committed:
                # Only a durably reserved Coin may be uncertain after a client crash.
                self.enqueue(p.COMMAND_SKIP_ITEM, index, state['epoch'])
            elif index < len(store.data['items']):
                item = store.data['items'][index][0]
                if item == 1:
                    # At-most-once consumables across process crashes. Never replay healing.
                    store.commit(index + 1)
                self.enqueue(item, index, state['epoch'])
        return f'Dolphin connected ({self.found["region"]}, file {state["slot"]}, {state["index"]} items)'

    def sync_deathlink(self, store, enabled, incoming_binding=None, incoming_text=None):
        """Exchange transient deaths only for a fully synchronized native file.

        Returns a local death edge. Received deaths never enter the item journal.
        """
        state = self.state()
        epoch, request, response, deaths = struct.unpack(
            '>4I', self.read(self.found['address'] + p.DEATH_LINK_OFFSET, 16))
        self.deathlink_request_pending = request != response
        ready = (state['slot'] != 0 and state['request'] == state['response'] and state['error'] == 0
                 and tuple(state['identity']) == store.token)
        active = bool(enabled and ready)
        current = (self.binding, deaths, active)
        previous = self.deathlink_state
        self.deathlink_state = current
        local_death = (active and previous is not None and previous[0] == self.binding
                       and previous[2] and deaths != previous[1])
        if not active:
            if epoch != 0:
                self.word(p.DEATH_LINK_EPOCH_OFFSET, 0, state['epoch'])
            return False
        if incoming_binding is not None and incoming_binding == self.binding:
            # Coalesce simultaneous remote deaths while one request is pending.
            if request == response:
                text = incoming_text or 'DeathLink'
                text = ''.join(c if (c == '\n' or c.isprintable()) and ord(c) <= 0xFFFF
                               and not 0xD800 <= ord(c) <= 0xDFFF else '?' for c in text)
                raw = text[:p.DEATH_LINK_TEXT_UNITS - 1].encode('utf-16-be')
                self.write(p.DEATH_LINK_TEXT_OFFSET, raw.ljust(p.DEATH_LINK_TEXT_UNITS * 2, b'\0'), state['epoch'])
                self.word(p.DEATH_LINK_EPOCH_OFFSET, state['epoch'], state['epoch'])
                self.word(p.DEATH_LINK_REQUEST_OFFSET, request + 1, state['epoch'])
        return bool(local_death)
