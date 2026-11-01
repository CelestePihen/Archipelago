"""Durable AP progress. This module has no network or emulator dependencies."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile

from .client_data import STAGES

ITEM_IDS = {1, 2, *range(100, 141), *range(200, 207)}
LOCATION_IDS = set(range(100001, 100121))


class StateError(RuntimeError):
    pass


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, sort_keys=True, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        if os.name != 'nt':
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def validate_slot_data(data: dict) -> dict:
    if not isinstance(data, dict):
        raise StateError('Missing SMG slot data')
    stars, mode = data.get('required_stars'), data.get('dome_unlock_mode')
    if type(stars) is not int or not 1 <= stars <= 121 or type(mode) is not int or mode not in (0, 1):
        raise StateError('Invalid required_stars or dome_unlock_mode in Connected.slot_data')
    return {'required_stars': stars, 'dome_unlock_mode': mode}


def location_for_star(stage: str, star: int) -> int:
    offset = 100000
    for name, count in STAGES:
        if stage == name:
            if type(star) is int and 1 <= star <= count:
                return offset + star
            break
        offset += count
    raise StateError(f'Unknown SMG check: {stage} star {star}')


def check_words(checks) -> list[int]:
    words = [0] * 4
    for location in checks:
        if location not in LOCATION_IDS:
            raise StateError(f'Unknown SMG location ID {location}')
        bit = location - 100001
        words[bit // 32] |= 1 << (bit % 32)
    return words


def decode_checks(words) -> set[int]:
    if len(words) != 4 or words[3] >> 24:
        raise StateError('Invalid check bitfield')
    return {100001 + bit for bit in range(120) if words[bit // 32] & (1 << (bit % 32))}


class ProgressStore:
    """One seed/team/slot journal, with a committed prefix of network items."""
    def __init__(self, directory: Path, seed: str, team: int, slot: int, slot_data: dict):
        if not seed or type(team) is not int or type(slot) is not int or team < 0 or slot < 1:
            raise StateError('The server did not supply a valid seed/team/slot identity')
        self.directory = directory
        identity = [seed, team, slot]
        digest = hashlib.sha256(json.dumps(identity, ensure_ascii=True).encode()).digest()[:16]
        self.token = struct.unpack('>4I', digest)
        self.path = directory / (digest.hex() + '.json')
        self.data = {'version': 1, 'identity': identity, 'slot_data': validate_slot_data(slot_data),
                     'items': [], 'committed': 0, 'checks': [], 'goal': False}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
                if (not isinstance(data, dict) or set(data) != set(self.data) or data['version'] != 1
                        or data['identity'] != identity or data['slot_data'] != self.data['slot_data']):
                    raise StateError('SMG journal identity, version or slot options do not match')
                self.validate_items(data['items'])
                if type(data['committed']) is not int or not 0 <= data['committed'] <= len(data['items']):
                    raise StateError('Invalid committed item cursor')
                if not isinstance(data['checks'], list) or any(type(c) is not int or c not in LOCATION_IDS for c in data['checks']):
                    raise StateError('Invalid cached checks')
                if type(data['goal']) is not bool:
                    raise StateError('Invalid cached goal')
                self.data = data
            except (ValueError, KeyError, TypeError) as exc:
                raise StateError(f'Cannot read SMG journal {self.path}: {exc}') from exc

    @staticmethod
    def validate_items(items):
        if not isinstance(items, list):
            raise StateError('Invalid item history')
        for item in items:
            if (not isinstance(item, list) or len(item) != 4 or any(type(v) is not int for v in item)
                    or item[0] not in ITEM_IDS):
                raise StateError(f'Unsupported SMG network item: {item}')

    def save(self):
        atomic_json(self.path, self.data)

    def update(self, **fields):
        # Keep the in-memory state unchanged if the disk commit fails: a retry
        # must still persist the update before any game/server acknowledgement.
        data = {**self.data, **fields}
        atomic_json(self.path, data)
        self.data = data

    def merge_items(self, items):
        incoming = [list(item) for item in items]
        self.validate_items(incoming)
        cached = self.data['items']
        if incoming[:len(cached)] != cached:
            raise StateError('Server item history conflicts with this seed journal; refusing item replay')
        if incoming != cached:
            self.update(items=incoming)

    def commit(self, index):
        if type(index) is not int or not self.data['committed'] <= index <= len(self.data['items']):
            raise StateError('Game item cursor conflicts with the durable journal')
        if index != self.data['committed']:
            self.update(committed=index)

    def record(self, checks=(), goal=False):
        checks = set(checks)
        check_words(checks)
        merged = sorted(set(self.data['checks']) | checks)
        completed = self.data['goal'] or goal
        if merged != self.data['checks'] or completed != self.data['goal']:
            self.update(checks=merged, goal=completed)

    def bind(self, profile: str, region: str, slot: int, character: int):
        """Keep a native file from silently switching to another AP seed."""
        path = self.directory / 'bindings.json'
        try:
            bindings = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            if not isinstance(bindings, dict):
                raise ValueError('expected an object')
        except (ValueError, TypeError) as exc:
            raise StateError(f'Invalid save bindings: {exc}') from exc
        key = json.dumps([profile, region, slot, character])
        identity = self.data['identity']
        if key in bindings and bindings[key] != identity:
            raise StateError('This Dolphin profile/save file is bound to another seed/slot. Select a new game file; '
                             'use --profile only for a different Dolphin user directory.')
        if key not in bindings:
            bindings[key] = identity
            atomic_json(path, bindings)

    def snapshot(self, epoch):
        stars, galaxies, domes = 0, [0, 0], 0
        for item, *_ in self.data['items'][:self.data['committed']]:
            if item == 2:
                stars += 1
            elif 100 <= item <= 140:
                bit = item - 100
                galaxies[bit // 32] |= 1 << (bit % 32)
            elif 200 <= item <= 206:
                domes |= 1 << (item - 200)
        config = self.data['slot_data']
        words = [epoch, *self.token, config['required_stars'], config['dome_unlock_mode'], stars,
                 *galaxies, domes, self.data['committed'], *check_words(self.data['checks']), int(self.data['goal'])]
        return struct.pack('>17I', *words)


class ClientLock:
    """Hold a process-scoped OS lock: one writer per client state directory."""
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.stream = (directory / 'client.lock').open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.stream.seek(0)
                self.stream.write(b'\0')
                self.stream.flush()
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.stream.close()
            raise StateError('Another SMG client already uses this state directory') from exc

    def close(self):
        self.stream.close()
