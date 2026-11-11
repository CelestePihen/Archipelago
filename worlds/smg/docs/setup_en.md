# Super Mario Galaxy setup

## Before you start

Install the SMG APWorld and use the latest patched game files. PAL (`RMGP01`)
and USA (`RMGE01`) are supported.

**Start a new save file for each new seed.** Keep the same save file when
returning to an existing seed.

If you run Archipelago from source, install the client dependency first:

```sh
.venv/bin/python -m pip install -r worlds/smg/requirements.txt
```

## Connecting

Open **Super Mario Galaxy Client** from Archipelago Launcher and enter your
server address, slot name and password, if needed.

From a source checkout, you can also start the client with:

```sh
.venv/bin/python -m worlds.smg.client --connect archipelago.gg:PORT --name SLOT
```

On Linux, let the client launch Dolphin so it can connect to the game:

```sh
.venv/bin/python -m worlds.smg.client --connect archipelago.gg:PORT --name SLOT \
  --launch /absolute/path/to/patched/game/DATA/sys/main.dol
```

Replace the server address, slot name and game path with your own.
Run only one Dolphin instance and one SMG client at a time.

Optional launch settings:

- `--dolphin /path/to/dolphin-emu`: choose a different Dolphin executable.
- `--dolphin-user /path/to/user`: use a separate Dolphin profile.
- `--nogui`: use the client in a terminal.

Closing the client leaves Dolphin open. After closing Dolphin,
`/dolphin_launch` in the client launches it again with the same settings.
This requires starting the client with `--launch`.

## Hint price

The Comet Luma offers hints for accessible Super Mario Galaxy checks.
New hints cost 100 Star Bits by default; reading purchased hints is free.
Set the price in your YAML before generating a seed:

```yaml
Super Mario Galaxy:
  hint_price: 100
```

## DeathLink

DeathLink shares deaths with other players who have enabled it.
You can configure it in your YAML before generating a seed:

```yaml
Super Mario Galaxy:
  death_link: true
  death_link_amnesty: 2
  death_link_group: ""
```

- **Amnesty:** with `2`, the first local death is spared and the second sends
  DeathLink, then the cycle starts again. `0` or `1` sends
  every local death. You can choose a value from 0 to 30. Deaths received from
  other players still apply normally and do not count toward amnesty.
- **Group:** leave it empty to use standard DeathLink, including games without
  group support. To share deaths only with a few players, choose the same
  group name in each compatible game, such as `"amis"`. Names are case-sensitive.

You can also change these settings in the client, including on an existing seed:

| Command | Effect |
| --- | --- |
| `/deathlink on` | Enable DeathLink. |
| `/deathlink off` | Disable DeathLink. |
| `/deathlink_amnesty 2` | Set amnesty to one DeathLink every two local deaths. |
| `/deathlink_group amis` | Join the group `amis`. |
| `/deathlink_group ""` | Return to standard DeathLink. |

For a group name with spaces, use quotes: `/deathlink_group "mes amis"`.
Use `/deathlink_amnesty` or `/deathlink_group` without a value to view the
current setting. Changes made in the client last until you close it.

## Saving and returning to your game

Save normally in the game. After a restart, reconnect to the same server and
slot, then load the same save file. Your AP Stars and Unlocks should return.
Checks completed during a network interruption are sent when you reconnect.
1-Ups already received are not granted again after restarting the game.

Keep both your Dolphin saves and the client's `smg-client` folder.
The `/dolphin` command shows the connection status and the client save location.
Copy both when moving to another computer.

If the client reports a save conflict or damaged progress file, keep those
files and ask for help before deleting anything.
