from __future__ import annotations
from enum import Enum
from typing import TYPE_CHECKING
from BaseClasses import Entrance, Region

if TYPE_CHECKING:
    from .world import SMGWorld


class SMGRegions(Enum):
    COMET_OBSERVATORY = "Comet Observatory"
    GOOD_EGG_GALAXY = "Good Egg Galaxy"


def create_and_connect_regions(world: SMGWorld) -> None:
    create_all_regions(world)
    connect_regions(world)


def create_all_regions(world: SMGWorld) -> None:
    regions = [Region(region.value, world.player, world.multiworld) for region in SMGRegions]
    world.multiworld.regions += regions


def connect_regions(world: SMGWorld) -> None:
    comet_observatory = world.get_region(SMGRegions.COMET_OBSERVATORY.value)

    for region in SMGRegions:
        if region.value == SMGRegions.COMET_OBSERVATORY.value:
            continue

        region_galaxy = world.get_region(region.value)
        comet_observatory_to_region = Entrance(world.player, f"{SMGRegions.COMET_OBSERVATORY.value} to {region.value}", comet_observatory)
        comet_observatory.exits.append(comet_observatory_to_region)
        comet_observatory_to_region.connect(region_galaxy)
