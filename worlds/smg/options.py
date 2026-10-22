from dataclasses import dataclass

from Options import Choice, Range, DeathLink, PerGameCommonOptions


class DomeUnlockMode(Choice):
    """Determines whether domes are accessible from the start or require Archipelago items."""
    display_name = "Dome Unlock Mode"
    option_all_open = 0
    option_individual = 1
    default = 0


class RequiredStars(Range):
    """Number of Power Stars required to access the final Bowser battle."""
    display_name = "Required Power Stars"
    range_start = 1
    range_end = 121
    default = 3


@dataclass
class SMGOptions(PerGameCommonOptions):
    death_link: DeathLink
    dome_unlock_mode: DomeUnlockMode
    required_stars: RequiredStars
