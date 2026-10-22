from __future__ import annotations
from enum import Enum
from typing import TYPE_CHECKING
from BaseClasses import Region

if TYPE_CHECKING:
    from .world import SMGWorld


class SMGRegions(Enum):
    # Comet Observatory
    COMET_OBSERVATORY = "Comet Observatory"
    SWEET_SWEET_GALAXY = "Sweet Sweet Galaxy"
    SLING_POD_GALAXY = "Sling Pod Galaxy"
    DRIP_DROP_GALAXY = "Drip Drop Galaxy"
    BIGMOUTH_GALAXY = "Bigmouth Galaxy"
    SAND_SPIRAL_GALAXY = "Sand Spiral Galaxy"
    SNOW_CAP_GALAXY = "Snow Cap Galaxy"
    BOOS_BONEYARD_GALAXY = "Boo's Boneyard Galaxy"
    BOWSERS_GALAXY_REACTOR = "Bowser's Galaxy Reactor"

    # Gate
    GATE = "Gate"
    GATEWAY_GALAXY = "Gateway Galaxy"

    # Terrace
    TERRACE = "Terrace"
    GOOD_EGG_GALAXY = "Good Egg Galaxy"
    HONEYHIVE_GALAXY = "Honeyhive Galaxy"
    LOOPDELOOP_GALAXY = "Loopdeeloop Galaxy"
    FLIPSWITCH_GALAXY = "Flipswitch Galaxy"
    BOWSER_JRS_ROBOT_REACTOR = "Bowser Jr.'s Robot Reactor"

    # Fountain
    FOUNTAIN = "Fountain"
    SPACE_JUNK_GALAXY = "Space Junk Galaxy"
    BATTLEROCK_GALAXY = "Battlerock Galaxy"
    ROLLING_GREEN_GALAXY = "Rolling Green Galaxy"
    HURRY_SCURRY_GALAXY = "Hurry-Scurry Galaxy"
    BOWSERS_STAR_REACTOR = "Bowser's Star Reactor"

    # Kitchen
    KITCHEN = "Kitchen"
    BEACH_BOWL_GALAXY = "Beach Bowl Galaxy"
    GHOSTLY_GALAXY = "Ghostly Galaxy"
    BUBBLE_BREEZE_GALAXY = "Bubble Breeze Galaxy"
    BUOY_BASE_GALAXY = "Buoy Base Galaxy"
    BOWSER_JRS_AIRSHIP_ARMADA = "Bowser Jr.'s Airship Armada"

    # Bedroom
    BEDROOM = "Bedroom"
    GUSTY_GARDEN_GALAXY = "Gusty Garden Galaxy"
    FREEZEFLAME_GALAXY = "Freezeflame Galaxy"
    DUSTY_DUNE_GALAXY = "Dusty Dune Galaxy"
    HONEYCLIMB_GALAXY = "Honeyclimb Galaxy"
    BOWSERS_DARK_MATTER_PLANT = "Bowser's Dark Matter Plant"

    # Engine Room
    ENGINE_ROOM = "Engine Room"
    GOLD_LEAF_GALAXY = "Gold Leaf Galaxy"
    SEA_SLIDE_GALAXY = "Sea Slide Galaxy"
    TOY_TIME_GALAXY = "Toy Time Galaxy"
    BONEFIN_GALAXY = "Bonefin Galaxy"
    BOWSER_JRS_LAVA_REACTOR = "Bowser Jr.'s Lava Reactor"

    # Garden
    GARDEN = "Garden"
    DEEP_DARK_GALAXY = "Deep Dark Galaxy"
    DREADNOUGHT_GALAXY = "Dreadnought Galaxy"
    MELTY_MOLTEN_GALAXY = "Melty Molten Galaxy"
    MATTER_SPLATTER_GALAXY = "Matter Splatter Galaxy"

    # Planet of Trials
    PLANET_OF_TRIALS = "Planet of Trials"
    ROLLING_GIZMO_GALAXY = "Rolling Gizmo Galaxy"
    BUBBLE_BLAST_GALAXY = "Bubble Blast Galaxy"
    LOOPDEESWOOP_GALAXY = "Loopdeeswoop Galaxy"
    GRAND_FINALE_GALAXY = "Grand Finale Galaxy"


DOMES: list[SMGRegions] = [
    SMGRegions.TERRACE,
    SMGRegions.FOUNTAIN,
    SMGRegions.KITCHEN,
    SMGRegions.BEDROOM,
    SMGRegions.ENGINE_ROOM,
    SMGRegions.GARDEN
]


REGION_GALAXIES: dict[SMGRegions, list[SMGRegions]] = {
    SMGRegions.COMET_OBSERVATORY: [
        SMGRegions.SWEET_SWEET_GALAXY,
        SMGRegions.SLING_POD_GALAXY,
        SMGRegions.DRIP_DROP_GALAXY,
        SMGRegions.BIGMOUTH_GALAXY,
        SMGRegions.SAND_SPIRAL_GALAXY,
        SMGRegions.SNOW_CAP_GALAXY,
        SMGRegions.BOOS_BONEYARD_GALAXY,
        SMGRegions.BOWSERS_GALAXY_REACTOR,
    ],

    SMGRegions.GATE: [
        SMGRegions.GATEWAY_GALAXY,
    ],

    SMGRegions.TERRACE: [
        SMGRegions.GOOD_EGG_GALAXY,
        SMGRegions.HONEYHIVE_GALAXY,
        SMGRegions.LOOPDELOOP_GALAXY,
        SMGRegions.FLIPSWITCH_GALAXY,
        SMGRegions.BOWSER_JRS_ROBOT_REACTOR,
    ],

    SMGRegions.FOUNTAIN: [
        SMGRegions.SPACE_JUNK_GALAXY,
        SMGRegions.BATTLEROCK_GALAXY,
        SMGRegions.ROLLING_GREEN_GALAXY,
        SMGRegions.HURRY_SCURRY_GALAXY,
        SMGRegions.BOWSERS_STAR_REACTOR,
    ],

    SMGRegions.KITCHEN: [
        SMGRegions.BEACH_BOWL_GALAXY,
        SMGRegions.GHOSTLY_GALAXY,
        SMGRegions.BUBBLE_BREEZE_GALAXY,
        SMGRegions.BUOY_BASE_GALAXY,
        SMGRegions.BOWSER_JRS_AIRSHIP_ARMADA,
    ],

    SMGRegions.BEDROOM: [
        SMGRegions.GUSTY_GARDEN_GALAXY,
        SMGRegions.FREEZEFLAME_GALAXY,
        SMGRegions.DUSTY_DUNE_GALAXY,
        SMGRegions.HONEYCLIMB_GALAXY,
        SMGRegions.BOWSERS_DARK_MATTER_PLANT,
    ],

    SMGRegions.ENGINE_ROOM: [
        SMGRegions.GOLD_LEAF_GALAXY,
        SMGRegions.SEA_SLIDE_GALAXY,
        SMGRegions.TOY_TIME_GALAXY,
        SMGRegions.BONEFIN_GALAXY,
        SMGRegions.BOWSER_JRS_LAVA_REACTOR,
    ],

    SMGRegions.GARDEN: [
        SMGRegions.DEEP_DARK_GALAXY,
        SMGRegions.DREADNOUGHT_GALAXY,
        SMGRegions.MELTY_MOLTEN_GALAXY,
        SMGRegions.MATTER_SPLATTER_GALAXY,
    ],

    SMGRegions.PLANET_OF_TRIALS: [
        SMGRegions.ROLLING_GIZMO_GALAXY,
        SMGRegions.BUBBLE_BLAST_GALAXY,
        SMGRegions.LOOPDEESWOOP_GALAXY,
        SMGRegions.GRAND_FINALE_GALAXY,
    ],
}


GALAXY_STAR_COUNTS: dict[SMGRegions, int] = {
    # Comet Observatory - Hungry Lumas
    SMGRegions.SWEET_SWEET_GALAXY: 1,
    SMGRegions.SLING_POD_GALAXY: 1,
    SMGRegions.DRIP_DROP_GALAXY: 1,
    SMGRegions.BIGMOUTH_GALAXY: 1,
    SMGRegions.SAND_SPIRAL_GALAXY: 1,
    SMGRegions.SNOW_CAP_GALAXY: 1,
    SMGRegions.BOOS_BONEYARD_GALAXY: 1,

    # Final Bowser
    SMGRegions.BOWSERS_GALAXY_REACTOR: 1,

    # Gate
    SMGRegions.GATEWAY_GALAXY: 2,

    # Terrace
    SMGRegions.GOOD_EGG_GALAXY: 6,
    SMGRegions.HONEYHIVE_GALAXY: 6,
    SMGRegions.LOOPDELOOP_GALAXY: 1,
    SMGRegions.FLIPSWITCH_GALAXY: 1,
    SMGRegions.BOWSER_JRS_ROBOT_REACTOR: 1,

    # Fountain
    SMGRegions.SPACE_JUNK_GALAXY: 6,
    SMGRegions.BATTLEROCK_GALAXY: 7,
    SMGRegions.ROLLING_GREEN_GALAXY: 1,
    SMGRegions.HURRY_SCURRY_GALAXY: 1,
    SMGRegions.BOWSERS_STAR_REACTOR: 1,

    # Kitchen
    SMGRegions.BEACH_BOWL_GALAXY: 6,
    SMGRegions.GHOSTLY_GALAXY: 6,
    SMGRegions.BUBBLE_BREEZE_GALAXY: 1,
    SMGRegions.BUOY_BASE_GALAXY: 2,
    SMGRegions.BOWSER_JRS_AIRSHIP_ARMADA: 1,

    # Bedroom
    SMGRegions.GUSTY_GARDEN_GALAXY: 6,
    SMGRegions.FREEZEFLAME_GALAXY: 6,
    SMGRegions.DUSTY_DUNE_GALAXY: 7,
    SMGRegions.HONEYCLIMB_GALAXY: 1,
    SMGRegions.BOWSERS_DARK_MATTER_PLANT: 1,

    # Engine Room
    SMGRegions.GOLD_LEAF_GALAXY: 6,
    SMGRegions.SEA_SLIDE_GALAXY: 6,
    SMGRegions.TOY_TIME_GALAXY: 6,
    SMGRegions.BONEFIN_GALAXY: 1,
    SMGRegions.BOWSER_JRS_LAVA_REACTOR: 1,

    # Garden
    SMGRegions.DEEP_DARK_GALAXY: 6,
    SMGRegions.DREADNOUGHT_GALAXY: 6,
    SMGRegions.MELTY_MOLTEN_GALAXY: 6,
    SMGRegions.MATTER_SPLATTER_GALAXY: 1,

    # Planet of Trials
    SMGRegions.ROLLING_GIZMO_GALAXY: 1,
    SMGRegions.BUBBLE_BLAST_GALAXY: 1,
    SMGRegions.LOOPDEESWOOP_GALAXY: 1,

    # Grand Finale
    SMGRegions.GRAND_FINALE_GALAXY: 1,
}


STARTING_GALAXIES = (
    SMGRegions.GOOD_EGG_GALAXY,
    SMGRegions.HONEYHIVE_GALAXY,
    SMGRegions.SPACE_JUNK_GALAXY,
    SMGRegions.BATTLEROCK_GALAXY,
    SMGRegions.BEACH_BOWL_GALAXY,
    SMGRegions.GHOSTLY_GALAXY,
    SMGRegions.GUSTY_GARDEN_GALAXY,
    SMGRegions.FREEZEFLAME_GALAXY,
    SMGRegions.DUSTY_DUNE_GALAXY,
    SMGRegions.GOLD_LEAF_GALAXY,
    SMGRegions.SEA_SLIDE_GALAXY,
    SMGRegions.TOY_TIME_GALAXY,
    SMGRegions.DEEP_DARK_GALAXY,
    SMGRegions.DREADNOUGHT_GALAXY,
    SMGRegions.MELTY_MOLTEN_GALAXY,
)


def create_and_connect_regions(world: SMGWorld) -> None:
    create_all_regions(world)
    connect_regions(world)


def create_all_regions(world: SMGWorld) -> None:
    regions = [Region(region.value, world.player, world.multiworld) for region in SMGRegions]
    world.multiworld.regions += regions


def connect_regions(world: SMGWorld) -> None:
    comet_observatory_region = world.get_region(SMGRegions.COMET_OBSERVATORY.value)

    for parent_region, galaxies in REGION_GALAXIES.items():
        parent = world.get_region(parent_region.value)

        # Observatory to dome
        if parent_region.value != SMGRegions.COMET_OBSERVATORY.value:
            comet_observatory_region.connect(parent, f"{SMGRegions.COMET_OBSERVATORY.value} to {parent_region.value}")

        # Dome to Galaxies
        for galaxy in galaxies:
            galaxy_region = world.get_region(galaxy.value)
            parent.connect(
                galaxy_region,
                f"{parent_region.value} to {galaxy.value}"
            )
