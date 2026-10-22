from __future__ import annotations
from typing import TYPE_CHECKING
from BaseClasses import Item, ItemClassification

if TYPE_CHECKING:
    from .world import SMGWorld


class ITEM:
    Star = "Star"
    Coin = "Coin"


ITEM_NAME_TO_ID = {
    ITEM.Star: 1,
    ITEM.Coin: 99
}

DEFAULT_ITEM_CLASSIFICATIONS = {
    ITEM.Star: ItemClassification.progression,
    ITEM.Coin: ItemClassification.filler
}


class SMGItem(Item):
    game: str = "Super Mario Galaxy"


def get_random_filler_item_name(world: SMGWorld) -> str:
    return ITEM.Coin


def create_item_with_correct_classification(world: SMGWorld, name: str) -> SMGItem:
    classification = DEFAULT_ITEM_CLASSIFICATIONS[name]

    return SMGItem(name, classification, ITEM_NAME_TO_ID[name], world.player)


def create_all_items(world: SMGWorld) -> None:
    itempool: list[Item] = []

    for _ in range(3):
        itempool.append(world.create_item("Star"))

    number_of_items = len(itempool)

    number_of_unfilled_locations = len(world.multiworld.get_unfilled_locations(world.player))

    needed_number_of_filler_items = number_of_unfilled_locations - number_of_items

    itempool += [world.create_filler() for _ in range(needed_number_of_filler_items)]

    world.multiworld.itempool += itempool