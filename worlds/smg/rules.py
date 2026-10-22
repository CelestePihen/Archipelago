from __future__ import annotations
from typing import TYPE_CHECKING

from rule_builder.rules import Has

from .items import ITEM
from .regions import DOMES, REGION_GALAXIES, SMGRegions
from .options import DomeUnlockMode

if TYPE_CHECKING:
    from .world import SMGWorld


def set_all_rules(world: SMGWorld) -> None:
    set_all_entrance_rules(world)
    set_all_location_rules(world)
    set_completion_condition(world)


def set_all_entrance_rules(world: SMGWorld) -> None:
    if world.options.dome_unlock_mode == DomeUnlockMode.option_individual:
        for dome in DOMES:
            entrance_name = f"Comet Observatory to {dome.value}"
            entrance = world.get_entrance(entrance_name)
            world.set_rule(entrance, Has(f"{dome.value} Unlock"))

    for parent, galaxies in REGION_GALAXIES.items():
        for galaxy in galaxies:
            # La grande étoile Gateway Galaxy est accessible sans item
            if galaxy == SMGRegions.GATEWAY_GALAXY:
                continue

            entrance_name = f"{parent.value} to {galaxy.value}"
            entrance = world.get_entrance(entrance_name)

            rule = Has(f"{galaxy.value} Unlock")

            # Bowser final nécessite également les Power Stars
            if galaxy == SMGRegions.BOWSERS_GALAXY_REACTOR:
                rule = rule & Has(ITEM.Star, count=world.options.required_stars.value)

            world.set_rule(entrance, rule)

    world.set_rule(world.get_entrance("Comet Observatory to Planet of Trials"), Has(ITEM.PlanetOfTrialsUnlock))


def set_all_location_rules(world: SMGWorld) -> None:
    gateway_second_star = world.get_location("Gateway Galaxy 2")
    world.set_rule(gateway_second_star, Has("Gateway Galaxy Unlock"))


def set_completion_condition(world: SMGWorld) -> None:
    world.set_completion_rule(Has(ITEM.Victory))
