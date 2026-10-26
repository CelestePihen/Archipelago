import json
from pathlib import Path

from worlds.AutoWorld import World
from . import items, locations, regions, rules
from . import options as smg_options


class SMGWorld(World):
    """
    Super Mario Galaxy is a 3D platformer developed by Nintendo for the Wii.
    Join Mario on an adventure across the universe, exploring unique galaxies,
    discovering new planets, and collecting Power Stars to unlock new areas.
    With gravity-defying gameplay, creative challenges, and a variety
    of power-ups, every galaxy offers something new to discover.
    The stars are waiting among the galaxies!
    """

    game = "Super Mario Galaxy"

    options_dataclass = smg_options.SMGOptions
    options: smg_options.SMGOptions

    location_name_to_id = locations.LOCATION_NAME_TO_ID
    item_name_to_id = items.ITEM_NAME_TO_ID

    origin_region_name = "Comet Observatory"

    def create_regions(self) -> None:
        regions.create_and_connect_regions(self)
        locations.create_all_locations(self)

    def set_rules(self) -> None:
        rules.set_all_rules(self)

    def create_items(self) -> None:
        items.create_all_items(self)

    def create_item(self, name: str) -> items.SMGItem:
        return items.create_item_with_correct_classification(self, name)

    def get_filler_item_name(self) -> str:
        return items.get_random_filler_item_name(self)

    def fill_slot_data(self) -> dict:
        return {"required_stars": self.options.required_stars.value}

    def generate_output(self, output_directory: str) -> None:
        # Même donnée que le paquet Connected du serveur, utilisable par le
        # client mailbox local sans modifier les flags de sauvegarde vanilla.
        name = self.multiworld.get_out_file_name_base(self.player) + ".smg.json"
        path = Path(output_directory) / name
        path.write_text(json.dumps(self.fill_slot_data(), indent=2) + "\n", encoding="utf-8")
