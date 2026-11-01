from .world import SMGWorld as SMGWorld

from worlds.LauncherComponents import Component, Type, components, launch


def run_client(*args):
    from .client import main
    launch(main, name='SuperMarioGalaxyClient', args=args)


components.append(Component('Super Mario Galaxy Client', func=run_client,
                            component_type=Type.CLIENT, game_name=SMGWorld.game, supports_uri=True))
