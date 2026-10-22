from __future__ import annotations
from typing import TYPE_CHECKING
from BaseClasses import Location
from .regions import SMGRegions

if TYPE_CHECKING:
    from .world import SMGWorld

LOCATION_NAME_TO_ID = {}

item_id_count = 100000

for region in SMGRegions:
    if region.value == SMGRegions.COMET_OBSERVATORY.value:
        continue

    for star in range(1, 3 + 1):
        item_id_count += 1
        LOCATION_NAME_TO_ID.update({f"{region.value} {star}": item_id_count})


class SMGLocation(Location):
    game = "Super Mario Galaxy"


def get_location_names_with_ids(location_names: list[str]) -> dict[str, int | None]:
    return {location_name: LOCATION_NAME_TO_ID[location_name] for location_name in location_names}


def create_all_locations(world: SMGWorld) -> None:
    create_regular_locations(world)


def create_regular_locations(world: SMGWorld) -> None:
    for smgregion in SMGRegions:
        if smgregion.value == SMGRegions.COMET_OBSERVATORY.value:
            continue

        region = world.get_region(smgregion.value)
        level_location = get_location_names_with_ids(
            [f"{smgregion.value} {star_count}" for star_count in range(1, 3 + 1)]
        )
        region.add_locations(level_location, SMGLocation)
