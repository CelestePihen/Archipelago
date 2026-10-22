from __future__ import annotations
from typing import TYPE_CHECKING
from BaseClasses import Item, ItemClassification

from .regions import DOMES, GALAXY_STAR_COUNTS, REGION_GALAXIES, STARTING_GALAXIES
from .options import DomeUnlockMode

if TYPE_CHECKING:
    from .world import SMGWorld


class ITEM:
    Star = "Star"
    Coin = "Coin"
    Victory = "Victory"
    PlanetOfTrialsUnlock = "Planet of Trials Unlock"


ITEM_NAME_TO_ID = {
    ITEM.Coin: 1,
    ITEM.Star: 2,
    ITEM.PlanetOfTrialsUnlock: 206
}

DEFAULT_ITEM_CLASSIFICATIONS = {
    ITEM.Coin: ItemClassification.filler,
    ITEM.Star: ItemClassification.progression_skip_balancing,
    ITEM.PlanetOfTrialsUnlock: ItemClassification.progression
}

for index, galaxy in enumerate(GALAXY_STAR_COUNTS, start=100):
    item_name = f"{galaxy.value} Unlock"

    ITEM_NAME_TO_ID[item_name] = index
    DEFAULT_ITEM_CLASSIFICATIONS[item_name] = ItemClassification.progression

for index, dome in enumerate(DOMES, start=200):
    item_name = f"{dome.value} Unlock"

    ITEM_NAME_TO_ID[item_name] = index
    DEFAULT_ITEM_CLASSIFICATIONS[item_name] = ItemClassification.progression


class SMGItem(Item):
    game: str = "Super Mario Galaxy"


def get_random_filler_item_name(world: SMGWorld) -> str:
    return ITEM.Coin


def create_item_with_correct_classification(world: SMGWorld, name: str) -> SMGItem:
    classification = DEFAULT_ITEM_CLASSIFICATIONS[name]

    return SMGItem(name, classification, ITEM_NAME_TO_ID[name], world.player)


def place_victory_event(world: SMGWorld) -> None:
    location = world.get_location("Bowser Defeated")

    victory_item = SMGItem(ITEM.Victory, ItemClassification.progression, None, world.player)

    location.place_locked_item(victory_item)


def set_starting_items(world: SMGWorld) -> set[str]:
    starting_galaxies = [
        (parent, galaxy)
        for parent, galaxies in REGION_GALAXIES.items() if parent in DOMES
        for galaxy in galaxies if galaxy in STARTING_GALAXIES
    ]

    starting_dome, starting_galaxy = world.random.choice(starting_galaxies)

    starting_items: set[str] = set()

    galaxy_item = f"{starting_galaxy.value} Unlock"
    world.multiworld.push_precollected(world.create_item(galaxy_item))
    starting_items.add(galaxy_item)
    
    dome_item = f"{starting_dome.value} Unlock"
    world.multiworld.push_precollected(world.create_item(dome_item))
    starting_items.add(dome_item)

    return starting_items


def create_all_items(world: SMGWorld) -> None:
    itempool: list[Item] = []

    starting_items: set[str] = set()

    if world.options.dome_unlock_mode == DomeUnlockMode.option_individual:
        starting_items = set_starting_items(world)

    for galaxy in GALAXY_STAR_COUNTS:
        item_name = f"{galaxy.value} Unlock"

        if item_name not in starting_items:
            itempool.append(world.create_item(item_name))

    if world.options.dome_unlock_mode == DomeUnlockMode.option_individual:
        for dome in DOMES:
            item_name = f"{dome.value} Unlock"

            if item_name not in starting_items:
                itempool.append(world.create_item(item_name))

    for _ in range(world.options.required_stars.value):
        itempool.append(world.create_item(ITEM.Star))

    # événement de victoire
    place_victory_event(world)

    # on met le reste des items par des items filler
    number_of_items = len(itempool)
    number_of_unfilled_locations = len(world.multiworld.get_unfilled_locations(world.player))
    needed_number_of_filler_items = number_of_unfilled_locations - number_of_items

    if needed_number_of_filler_items < 0:
        raise ValueError(f"Too many items: {number_of_items} items for {number_of_unfilled_locations} locations")

    itempool += [world.create_filler() for _ in range(needed_number_of_filler_items)]

    world.multiworld.itempool += itempool