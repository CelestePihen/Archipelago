# Super Mario Galaxy client

Install the SMG APWorld and `dolphin-memory-engine>=1.3.1` in the same Python
environment as Archipelago. The client appears as **Super Mario Galaxy Client**
in Archipelago Launcher. It uses the standard server address, slot name and
password UI. DeathLink is not implemented yet.

The game must use the **mailbox v5** module and matching patched DOL/bootstrap.
Rebuild both PAL/USA artifacts and restart Dolphin when upgrading from v4.
PAL (`RMGP01`) and USA (`RMGE01`) are supported. Use a new game file for a new
seed: existing native star flags count as completed checks.

From an Archipelago source checkout:

```sh
.venv/bin/python -m pip install -r worlds/smg/requirements.txt
.venv/bin/python -m worlds.smg.client --connect archipelago.gg:PORT --name SLOT
```

On Linux, process permissions may prevent attachment to Dolphin launched
independently. Let the client start Dolphin as its child; no system permission
changes or administrator privileges are required:

```sh
.venv/bin/python -m worlds.smg.client --connect archipelago.gg:PORT --name SLOT \
  --launch /absolute/path/to/patched/game/DATA/sys/main.dol
```

Use `--dolphin /path/to/dolphin-emu` for a non-default executable,
`--dolphin-user /path/to/user` for a separate Dolphin user directory, and
`--nogui` for terminal use. Run only one Dolphin game and one SMG mailbox writer
at a time. Closing the client leaves Dolphin running.

## Resuming

After the first connection, the client stores the received item history,
accepted item prefix, checked locations and victory in its `smg-client` user
directory. `/dolphin` prints the current status and journal path. Keep that
directory with the Dolphin saves; `--state-dir PATH` can choose its location.
No server password is stored in the SMG journal.

* Network disconnect: gameplay checks are written locally before their mailbox
  acknowledgement. They are resent on reconnection, including victory.
* Client restart: reconnect to the same room/slot. The game-owned item cursor
  prevents receiving the same indexed item twice.
* Dolphin restart or older savestate: Stars and Unlocks are restored from the
  journal. Native save flags recover checks made without the client, including
  a full transient event queue. Save the game normally; unsaved native gameplay
  cannot be reconstructed if both processes disappear before it is recorded.
* Coins are consumables. Previously accepted Coins are not replayed to heal the
  player again, and temporary pending effects are not restored after a game
  restart. A crash between durable reservation and delivery can lose the Coin
  in flight; it cannot duplicate it.

The client binds each native file (region, file number and Mario/Luigi) to a
seed/team/slot and refuses a conflicting seed. For a genuinely separate Dolphin
user directory, use `--dolphin-user` or a distinct `--profile` name. Do not change
the profile name merely to bypass a conflicting save binding. To move to another
computer, copy the game saves and the entire SMG client state directory.

If the client reports a corrupt journal or conflicting history, preserve the
files for diagnosis. It stops syncing rather than guessing an item cursor.

## Validation boundary

Unit tests cover disk failures, repeated item packets, item/seed isolation,
offline check and goal delivery, and a real local WebSocket handshake. PAL/USA
PowerPC tests execute the compiled restoration and deduplication code with
simulated save/player/UI services. These do not replace a complete real seed
playthrough and rendered Dolphin reconnect/restart testing.
