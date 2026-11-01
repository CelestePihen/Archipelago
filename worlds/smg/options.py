from dataclasses import dataclass

from Options import Choice, Range, DeathLink, PerGameCommonOptions
from .regions import DOMES, GALAXY_STAR_COUNTS, SMGRegions


class DomeUnlockMode(Choice):
    """Determines whether domes are accessible from the start or require Archipelago items."""
    display_name = "Dome Unlock Mode"
    option_all_open = 0
    option_individual = 1
    default = 0


def max_required_stars(dome_unlock_mode: int) -> int:
    """Fit Stars and Unlocks before the final Bowser check."""
    unlocks = len(GALAXY_STAR_COUNTS)
    if dome_unlock_mode == DomeUnlockMode.option_individual:
        # One starting galaxy and its dome are automatically precollected.
        unlocks += len(DOMES) - 2
    pre_goal_checks = sum(count for galaxy, count in GALAXY_STAR_COUNTS.items()
                          if galaxy != SMGRegions.BOWSERS_GALAXY_REACTOR)
    return pre_goal_checks - unlocks


class RequiredStars(Range):
    """Number of Power Stars required to access the final Bowser battle.

    Maximum: 78 with all domes open, 73 with individual dome unlocks.
    Unlock items also need locations, and Bowser's own check cannot hold
    progression needed to reach him.
    """
    display_name = "Required Power Stars"
    range_start = 1
    range_end = max_required_stars(DomeUnlockMode.option_all_open)
    default = 3


@dataclass
class SMGOptions(PerGameCommonOptions):
    death_link: DeathLink
    dome_unlock_mode: DomeUnlockMode
    required_stars: RequiredStars
