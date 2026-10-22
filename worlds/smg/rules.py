from __future__ import annotations
from typing import TYPE_CHECKING

from rule_builder.rules import Has

from .items import ITEM

if TYPE_CHECKING:
    from .world import SMGWorld


def set_all_rules(world: SMGWorld) -> None:
    set_completion_condition(world)


def set_completion_condition(world: SMGWorld) -> None:
    world.set_completion_rule(Has(ITEM.Star, count=3))
