"""Super Mario Galaxy Archipelago client, using the standard CommonContext UI."""
from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess

import Utils
from CommonClient import CommonContext, ClientCommandProcessor, get_base_parser, handle_url_arg, logger, server_loop
from NetUtils import ClientStatus

from .client_state import ClientLock, ProgressStore, StateError
from .dolphin import DolphinBridge, DolphinUnavailable


class SMGCommandProcessor(ClientCommandProcessor):
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
                self.progress = ProgressStore(self.state_dir, self.server_seed_name, self.team, self.slot, args['slot_data'])
                self.progress.save()
                self.sent_checks = set(self.checked_locations)
                self.goal_sent = False
                self.history_ready = False
                self.client_error = None
            elif cmd == 'ReceivedItems' and self.progress:
                if args['index'] == 0:
                    self.history_ready = True
                if self.history_ready:
                    self.progress.merge_items(self.items_received)
            elif cmd == 'RoomUpdate':
                self.sent_checks.update(args.get('checked_locations', ()))
        except (StateError, OSError) as exc:
            self.client_error = str(exc)
            logger.error('SMG sync stopped: %s', exc)
        self.watcher_event.set()

    async def sync_once(self):
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
