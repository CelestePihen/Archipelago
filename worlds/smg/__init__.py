from ..AutoWorld import World
from BaseClasses import Region


class SMGWorld(World):
    """
    The World for Super Mario Galaxy on Wii
    """

    game = "Super Mario Galaxy"

    item_name_to_id = {}

    location_name_to_id = {

    }

    def create_regions(self) -> None:
        menu_region = Region("Menu", self.player, self.multiworld)

        self.multiworld.regions += [menu_region]
