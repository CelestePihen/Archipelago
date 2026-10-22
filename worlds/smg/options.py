from dataclasses import dataclass

from Options import DeathLink, PerGameCommonOptions


@dataclass
class SMGOptions(PerGameCommonOptions):
    death_link: DeathLink
