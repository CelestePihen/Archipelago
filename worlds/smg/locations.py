from __future__ import annotations
from typing import TYPE_CHECKING
from BaseClasses import Location

from .regions import GALAXY_STAR_COUNTS, SMGRegions

if TYPE_CHECKING:
    from .world import SMGWorld

LOCATION_NAME_TO_ID = {}

location_id_count = 100000

for galaxy, star_count in GALAXY_STAR_COUNTS.items():
    for star in range(1, star_count + 1):
        location_id_count += 1
        LOCATION_NAME_TO_ID[f"{galaxy.value} {star}"] = location_id_count


class SMGLocation(Location):
    game = "Super Mario Galaxy"


def get_location_names_with_ids(location_names: list[str]) -> dict[str, int | None]:
    return {location_name: LOCATION_NAME_TO_ID[location_name] for location_name in location_names}


def create_all_locations(world: SMGWorld) -> None:
    create_regular_locations(world)
    create_event_locations(world)


def create_regular_locations(world: SMGWorld) -> None:
    for galaxy, star_count in GALAXY_STAR_COUNTS.items():
        region_parent = world.get_region(galaxy.value)

        level_location = get_location_names_with_ids(
            [f"{galaxy.value} {star}" for star in range(1, star_count + 1)]
        )
        region_parent.add_locations(level_location, SMGLocation)


def create_event_locations(world: SMGWorld) -> None:
    bowser_region = world.get_region(SMGRegions.BOWSERS_GALAXY_REACTOR.value)

    victory_location = SMGLocation(world.player, "Bowser Defeated", None, bowser_region)
    bowser_region.locations.append(victory_location)