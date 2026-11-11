"""Super Mario Galaxy Archipelago client, using the standard CommonContext UI."""
from __future__ import annotations

import asyncio
from collections import deque
import math
from pathlib import Path
import subprocess
import textwrap
import time

import Utils
from CommonClient import CommonContext, ClientCommandProcessor, get_base_parser, handle_url_arg, logger, server_loop
from NetUtils import ClientStatus

from .client_state import ClientLock, ProgressStore, StateError
from .dolphin import DolphinBridge, DolphinUnavailable
from .options import DeathLinkAmnesty, DeathLinkGroup


class SMGCommandProcessor(ClientCommandProcessor):
    def _cmd_deathlink(self, setting: str = ''):
        """Toggle DeathLink, or use /deathlink on or /deathlink off (overrides the seed for this client session)."""
        if setting.lower() not in ('', 'on', 'off'):
            self.output('Usage: /deathlink [on|off]')
            return False
        enabled = not self.ctx.deathlink_enabled if not setting else setting.lower() == 'on'
        if enabled != self.ctx.deathlink_enabled:
            self.ctx.deathlink_deaths = 0
            self.ctx.deathlink_cancel_pending = True
        self.ctx.deathlink_override = enabled
        self.ctx.deathlink_enabled = enabled
        self.ctx.deathlink_pending = None
        self.ctx.deathlink_pending_text = None
        if self.ctx.bridge:
            self.ctx.bridge.deathlink_state = None
        self.output(f'DeathLink {"enabled" if enabled else "disabled"}.')
        return True

    def _cmd_deathlink_group(self, group: str | None = None):
        """Show the group, or set /deathlink_group NAME for this session. Quote names with spaces; use /deathlink_group "" for standard DeathLink."""
        if group is not None:
            try:
                self.ctx.set_deathlink_group(group)
            except StateError as exc:
                self.output(f'Invalid DeathLink group: {exc}')
                return False
            self.ctx.deathlink_group_override = group
        self.output(f'DeathLink group: {self.ctx.deathlink_group!r}'
                    if self.ctx.deathlink_group else 'DeathLink group: standard (empty group).')
        return True

    def _cmd_deathlink_amnesty(self, value: str = ''):
        """Show amnesty, or set /deathlink_amnesty 0..30 for this client session. Send every Nth local death (0 or 1 sends all)."""
        if value:
            try:
                amnesty = int(value)
                self.ctx.set_deathlink_amnesty(amnesty)
            except (ValueError, StateError) as exc:
                self.output(f'Invalid DeathLink amnesty: {exc}')
                return False
            self.ctx.deathlink_amnesty_override = amnesty
        self.output(f'DeathLink amnesty: {self.ctx.deathlink_amnesty}; '
                    f'{self.ctx.deathlink_deaths} local deaths spared in the current cycle.')
        return True

    def _cmd_dolphin_launch(self):
        """Launch Dolphin again with the original --launch, --dolphin and --dolphin-user settings. Close Dolphin first."""
        try:
            self.ctx.launch_dolphin()
        except (StateError, OSError, RuntimeError) as exc:
            self.output(f'Cannot launch Dolphin: {exc}')
            return False
        self.output('Dolphin launched. Load your save file to resume Archipelago synchronization.')
        return True

    def _cmd_dolphin(self):
        """Show the emulator connection and durable journal status."""
        self.output(self.ctx.dolphin_status)
        if self.ctx.progress:
            self.output(f'Journal: {self.ctx.progress.path}')


class SMGContext(CommonContext):
    game = 'Super Mario Galaxy'
    items_handling = 0b111
    command_processor = SMGCommandProcessor

    def __init__(self, server_address=None, password=None, *, state_dir=None, memory=None, profile='default',
                 launch_path=None, dolphin='dolphin-emu', dolphin_user=None):
        super().__init__(server_address, password)
        self.state_dir = Path(state_dir) if state_dir else Path(Utils.user_path('smg-client'))
        self.progress = None
        self.profile = profile
        self.bridge = DolphinBridge(memory, profile) if memory is not None else None
        self.dolphin_status = 'Waiting for Archipelago connection'
        self.client_error = None
        self.sent_checks = set()
        self.goal_sent = False
        self.history_ready = False
        self.launch_path = Path(launch_path).resolve() if launch_path else None
        self.dolphin_executable = dolphin
        self.dolphin_user = Path(dolphin_user).resolve() if dolphin_user else None
        self.dolphin_process = None
        self.deathlink_enabled = False
        self.deathlink_override = None
        self.deathlink_pending = None
        self.deathlink_pending_text = None
        self.deathlink_seen = deque(maxlen=128)
        self.deathlink_amnesty = 0
        self.deathlink_amnesty_override = None
        self.deathlink_deaths = 0
        self.deathlink_group = ''
        self.deathlink_group_override = None
        self.deathlink_subscription = None
        self.deathlink_cancel_pending = False

    @property
    def deathlink_tag(self):
        # Shared by PEAK, GodotAP/BK Simulator and DELTARUNE: no separator or
        # case normalization. An empty group keeps the standard DeathLink tag.
        return 'DeathLink' + self.deathlink_group

    def set_deathlink_group(self, value):
        if not isinstance(value, str):
            raise StateError('Expected a DeathLink group name as text')
        try:
            DeathLinkGroup.validate_text(value)
        except ValueError as exc:
            raise StateError(str(exc)) from exc
        if value != self.deathlink_group:
            self.deathlink_pending = None
            self.deathlink_pending_text = None
            self.deathlink_deaths = 0
            self.deathlink_cancel_pending = True
            if self.bridge:
                self.bridge.deathlink_state = None
        self.deathlink_group = value

    async def update_death_link(self, death_link):
        old_tags = self.tags.copy()
        if self.deathlink_subscription is not None:
            self.tags.discard(self.deathlink_subscription)
        self.tags.discard('DeathLink')
        self.deathlink_subscription = self.deathlink_tag if death_link else None
        if self.deathlink_subscription is not None:
            self.tags.add(self.deathlink_subscription)
        if old_tags != self.tags and self.server and not self.server.socket.closed:
            await self.send_msgs([{'cmd': 'ConnectUpdate', 'tags': self.tags.copy()}])

    async def send_death(self, death_text=''):
        if self.server and self.server.socket and not self.server.socket.closed:
            logger.info('DeathLink: Sending death to your friends...')
            self.last_death_link = time.time()
            await self.send_msgs([{'cmd': 'Bounce', 'tags': [self.deathlink_tag],
                                   'data': {'time': self.last_death_link,
                                            'source': self.player_names[self.slot], 'cause': death_text}}])

    def set_deathlink_amnesty(self, value):
        if type(value) is not int or not DeathLinkAmnesty.range_start <= value <= DeathLinkAmnesty.range_end:
            raise StateError(f'Expected an integer from {DeathLinkAmnesty.range_start} to {DeathLinkAmnesty.range_end}')
        if value != self.deathlink_amnesty:
            self.deathlink_deaths = 0
        self.deathlink_amnesty = value

    def on_deathlink(self, data):
        # CommonClient dispatches only the ungrouped tag here. Grouped packets
        # are dispatched explicitly in on_package, after checking their tag.
        if not self.deathlink_group:
            self.receive_deathlink(data)

    def receive_deathlink(self, data):
        if not self.deathlink_enabled or not self.server or self.slot is None:
            return
        if not isinstance(data, dict):
            return
        timestamp, source = data.get('time'), data.get('source')
        if (type(timestamp) not in (int, float) or not math.isfinite(timestamp) or timestamp <= 0
                or not isinstance(source, str) or not source or not isinstance(data.get('cause', ''), str)):
            return
        if source == self.player_names.get(self.slot):
            return  # Also ignore a delayed own echo after another player's death.
        key = (timestamp, source)
        if key in self.deathlink_seen or timestamp == self.last_death_link:
            return
        self.deathlink_seen.append(key)
        super().on_deathlink(data)
        if self.bridge and self.history_ready and self.bridge.binding is not None:
            self.deathlink_pending = self.bridge.binding
            self.deathlink_pending_text = self.deathlink_message(source, data.get('cause', ''))

    def deathlink_message(self, source, cause=''):
        # Sources may be slot names, current aliases or arbitrary in-game names.
        # Use server metadata only when it identifies exactly one player.
        matches = [info for slot, info in self.slot_info.items() if slot > 0
                   and source in (info.name, self.player_names.get(slot))]
        game = matches[0].game if len(matches) == 1 else None

        def clean(value):
            value = ''.join(c if c.isprintable() and ord(c) <= 0xFFFF and not 0xD800 <= ord(c) <= 0xDFFF
                            else ' ' for c in value)
            return ' '.join(value.split())

        def label(value, limit):
            value = clean(value)
            return value if len(value) <= limit else value[:limit - 3] + '...'

        message = clean(cause)
        if not message:
            message = label(source, 24) + ' died'
            if game:
                message += ' in ' + label(game, 32)
            message += '.'
        # Fit the native centered window and its 80-unit UTF-16 channel.
        lines = textwrap.wrap(message, width=34, max_lines=2, placeholder='...', break_on_hyphens=False)
        return 'DeathLink\n' + '\n'.join(lines)

    def launch_dolphin(self):
        if self.launch_path is None:
            raise StateError('Start the client with --launch /path/to/patched/main.dol first')
        if not self.launch_path.is_file():
            raise StateError(f'Game path does not exist: {self.launch_path}')
        if self.dolphin_process is not None and self.dolphin_process.poll() is None:
            raise StateError('Dolphin is still running. Close its window before launching it again')
        if self.bridge is not None:
            # Discard the old process attachment and probe for another Dolphin
            # before spawning. Keep the seed journal and network session intact.
            self.bridge.forget()
            self.bridge.memory.un_hook()
            self.bridge.memory.hook()
            if self.bridge.memory.is_hooked():
                raise StateError('Another Dolphin instance is running. Close it before launching Dolphin here')
        command = [self.dolphin_executable, '-e', str(self.launch_path)]
        if self.dolphin_user:
            command += ['-u', str(self.dolphin_user)]
        self.dolphin_process = subprocess.Popen(command)

    async def server_auth(self, password_requested=False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd, args):
        try:
            if cmd == 'Connected':
                old_token = self.progress.token if self.progress else None
                self.progress = ProgressStore(self.state_dir, self.server_seed_name, self.team, self.slot, args['slot_data'])
                self.progress.save()
                self.sent_checks = set(self.checked_locations)
                self.goal_sent = False
                self.history_ready = False
                self.client_error = None
                enabled = (bool(args['slot_data'].get('death_link', False))
                           if self.deathlink_override is None else self.deathlink_override)
                if old_token != self.progress.token or enabled != self.deathlink_enabled:
                    self.deathlink_deaths = 0
                self.deathlink_enabled = enabled
                self.set_deathlink_amnesty(args['slot_data'].get('death_link_amnesty', 0)
                                           if self.deathlink_amnesty_override is None else self.deathlink_amnesty_override)
                self.set_deathlink_group(args['slot_data'].get('death_link_group', '')
                                         if self.deathlink_group_override is None else self.deathlink_group_override)
                self.deathlink_pending = None
                self.deathlink_pending_text = None
                self.deathlink_cancel_pending = True
                if self.bridge:
                    self.bridge.deathlink_state = None
            elif cmd == 'ReceivedItems' and self.progress:
                if args['index'] == 0:
                    self.history_ready = True
                if self.history_ready:
                    self.progress.merge_items(self.items_received)
            elif cmd == 'RoomUpdate':
                self.sent_checks.update(args.get('checked_locations', ()))
            elif cmd == 'Bounced' and self.deathlink_group:
                tags = args.get('tags', [])
                if isinstance(tags, (list, set, tuple)) and self.deathlink_tag in tags:
                    self.receive_deathlink(args.get('data'))
        except (StateError, OSError) as exc:
            self.client_error = str(exc)
            logger.error('SMG sync stopped: %s', exc)
        self.watcher_event.set()

    async def sync_once(self):
        await self.update_death_link(self.deathlink_enabled)
        if self.client_error:
            return
        if not self.progress or not self.history_ready:
            return
        if self.bridge is None:
            try:
                import dolphin_memory_engine
            except ImportError as exc:
                raise StateError('Install the SMG client dependency: dolphin-memory-engine>=1.3.1') from exc
            self.bridge = DolphinBridge(dolphin_memory_engine, self.profile)
        status = self.bridge.tick(self.progress)
        connected = bool(self.deathlink_enabled and self.server and self.slot is not None
                         and self.server.socket and not self.server.socket.closed)
        if self.deathlink_cancel_pending:
            # A death already published for the old group must be cancelled and
            # acknowledged before a death from the new group can be submitted.
            self.bridge.sync_deathlink(self.progress, False)
            self.deathlink_cancel_pending = self.bridge.deathlink_request_pending
        if self.deathlink_cancel_pending:
            local_death = False
            if not connected:
                self.deathlink_pending = None
                self.deathlink_pending_text = None
        else:
            local_death = self.bridge.sync_deathlink(self.progress, connected,
                                                    self.deathlink_pending if connected else None,
                                                    self.deathlink_pending_text if connected else None)
            self.deathlink_pending = None
            self.deathlink_pending_text = None
        if local_death:
            self.deathlink_deaths += 1
            if self.deathlink_deaths < self.deathlink_amnesty:
                logger.info('DeathLink Amnesty %s/%s', self.deathlink_deaths, self.deathlink_amnesty)
            else:
                self.deathlink_deaths = 0
                await self.send_death(f'{self.player_names[self.slot]} died in Super Mario Galaxy.')
        if status != self.dolphin_status:
            # Keep /dolphin current without announcing each received item as
            # a new emulator connection. Region/file and state changes still log.
            count_only = (status.startswith('Dolphin connected (')
                          and self.dolphin_status.startswith('Dolphin connected (')
                          and status.rsplit(', ', 1)[0] == self.dolphin_status.rsplit(', ', 1)[0])
            self.dolphin_status = status
            if not count_only:
                logger.info(status)
        if self.server and self.slot is not None:
            pending = set(self.progress.data['checks']) - self.sent_checks
            if pending:
                await self.send_msgs([{'cmd': 'LocationChecks', 'locations': sorted(pending)}])
                self.locations_checked.update(pending)
                self.sent_checks.update(pending)
            if self.progress.data['goal'] and not self.goal_sent:
                await self.send_msgs([{'cmd': 'StatusUpdate', 'status': ClientStatus.CLIENT_GOAL}])
                self.finished_game = True
                self.goal_sent = True

    def make_gui(self):
        ui = super().make_gui()
        ui.base_title = 'Archipelago Super Mario Galaxy Client'
        return ui


async def dolphin_loop(ctx):
    while not ctx.exit_event.is_set():
        try:
            await ctx.sync_once()
        except StateError as exc:
            ctx.client_error = str(exc)
            logger.error('SMG sync stopped: %s', exc)
        except (RuntimeError, OSError) as exc:
            if ctx.bridge:
                ctx.bridge.forget()
                try:
                    ctx.bridge.memory.un_hook()
                except (RuntimeError, OSError):
                    pass
            message = f'Dolphin unavailable: {exc}. On Linux, use --launch if process permissions prevent attachment.'
            if message != ctx.dolphin_status:
                ctx.dolphin_status = message
                logger.info(message)
        try:
            await asyncio.wait_for(ctx.exit_event.wait(), timeout=0.1 if ctx.bridge and ctx.bridge.found else 2.0)
        except asyncio.TimeoutError:
            pass


def main(*args):
    parser = get_base_parser('Super Mario Galaxy Archipelago Client')
    parser.add_argument('--name', help='Archipelago slot name')
    parser.add_argument('--state-dir', type=Path, help='Durable client journal directory')
    parser.add_argument('--profile', default='default', help='Name identifying a distinct Dolphin user directory')
    parser.add_argument('--launch', type=Path, help='Launch Dolphin as a child (recommended on Linux)')
    parser.add_argument('--dolphin', default='dolphin-emu', help='Dolphin executable path')
    parser.add_argument('--dolphin-user', type=Path, help='Optional Dolphin user directory')
    parser.add_argument('url', nargs='?', help='archipelago:// connection URL')
    parsed = handle_url_arg(parser.parse_args(args), parser)
    if getattr(parsed, 'nogui', False):
        import CommonClient
        Utils.gui_enabled = CommonClient.gui_enabled = False
    Utils.init_logging('Super Mario Galaxy Client')

    async def run():
        ctx = SMGContext(parsed.connect, parsed.password, state_dir=parsed.state_dir,
                         launch_path=parsed.launch, dolphin=parsed.dolphin, dolphin_user=parsed.dolphin_user)
        ctx.auth = parsed.name
        lock = ClientLock(ctx.state_dir)
        sync_task = None
        try:
            try:
                import dolphin_memory_engine
            except ImportError as exc:
                raise StateError('Missing dolphin-memory-engine. Install the dependencies from worlds/smg/requirements.txt.') from exc
            profile = str(parsed.dolphin_user.resolve()) if parsed.dolphin_user else parsed.profile
            ctx.bridge = DolphinBridge(dolphin_memory_engine, profile)
            if parsed.launch:
                try:
                    ctx.launch_dolphin()
                except (StateError, OSError, RuntimeError) as exc:
                    logger.error('Cannot launch Dolphin: %s. Use /dolphin_launch to retry.', exc)
            ctx.server_task = asyncio.create_task(server_loop(ctx), name='SMG server')
            if Utils.gui_enabled and not getattr(parsed, 'nogui', False):
                ctx.run_gui()
            ctx.run_cli()
            sync_task = asyncio.create_task(dolphin_loop(ctx), name='SMG Dolphin')
            await ctx.exit_event.wait()
        finally:
            ctx.exit_event.set()
            if sync_task:
                await sync_task
            await ctx.shutdown()
            if ctx.bridge:
                ctx.bridge.memory.un_hook()
            # Dolphin and its saves stay open when the network client exits.
            lock.close()

    import colorama
    colorama.just_fix_windows_console()
    try:
        asyncio.run(run())
    except StateError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        colorama.deinit()


if __name__ == '__main__':
    import sys
    main(*sys.argv[1:])
