''' Initiates jocular, checking if we have a data directory
'''

import os
import sys
import click
import glob
import json
from datetime import datetime
from pathlib import Path

from jocular import __version__

def get_datadir():
    try:
        with open(os.path.join(str(Path.home()), '.jocular'), 'r') as f:
            return f.read().strip()
    except:
        return None

def print_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.echo('Version {:}'.format(__version__))
    ctx.exit()

@click.command()
@click.option(
    '--datadir',
    type=click.Path(exists=True),
    default=get_datadir(),
    show_default=True,
    help='where to store Jocular data',
)
@click.option(
    '--log',
    show_default=True,
    type=click.Choice(['error', 'warning', 'debug'], case_sensitive=False),
    default='error',
)
@click.option('--version', '-v', is_flag=True, callback=print_version,
              expose_value=False, is_eager=True)
@click.option('--rebuildobservations', '-r', is_flag=True, default=False,
    show_default=True,
    expose_value=True, is_eager=True,
    help='Construct observations file by scanning captures')
def startjocular(datadir, log, rebuildobservations):

    # stop Kivy from interpreting any args
    os.environ["KIVY_NO_ARGS"] = "1"

    if datadir is None:
        print()
        print('  Jocular cannot find your data directory. This might be because')
        print('  this is the first time you have used Jocular (welcome!), or')
        print('  because you have moved it. Please specify it using the --datadir')
        print('  option e.g.')
        print('  ')
        print('    jocular --datadir /Users/Martin/JocularData')
        print('  ')
        print('  Note that the directory must already exist, so if you are')
        print('  starting to use Jocular for the first time, please create')
        print('  the directory before running the command. You will not need')
        print('  to specify the datadir on subsequent runs of Jocular unless')
        print('  you have changed its location, in which case you will see')
        print('  this message.')
        print()
        sys.exit()

    # ensure we are using absolute paths so that user can start from any place
    datadir = os.path.abspath(datadir)

    # store absolute path to datadir in .jocular
    try:
        with open(os.path.join(str(Path.home()), '.jocular'), 'w') as f:
            f.write(datadir)
    except Exception as e:
        sys.exit(
            'Unable to write .jocular in home directory {:} ({:})'.format(
                str(Path.home()), e
            )
        )

    # timestamp in datadir, which checks it is writeable
    try:
        with open(os.path.join(datadir, '.lastwritten'), 'w') as f:
            f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    except Exception as e:
        sys.exit('Unable to write to user data directory {:} ({:})'.format(datadir, e))

    # # rebuild observations by moving observations.json to deleted folder
    # if rebuildobservations:
    #     try:
    #         from jocular.utils import move_to_dir
    #         from jocular.metadata import get_metadata

    #         pth = os.path.join(datadir, 'previous_observations.json')
    #         if os.path.exists(pth):
    #             move_to_dir(pth, os.path.join(datadir, 'deleted'))
    #     except Exception as e:
    #         print('exception moving prev obs', e)
    #         # pass

    # alternative approach that ensures observations are rebuilt
    # before GUI is launched, preventing possible races
    obspath = os.path.join(datadir, 'previous_observations.json')
    if rebuildobservations or not os.path.exists(obspath):
        try:
            from jocular.utils import move_to_dir
            from jocular.metadata import get_metadata

            # move prev to deleted in case user wishes to restore
            pth = os.path.join(datadir, 'previous_observations.json')
            if os.path.exists(obspath):
                move_to_dir(obspath, os.path.join(datadir, 'deleted'))

            # extract all observational data from captures
            observations = {}
            for sesh in glob.glob(os.path.join(datadir, 'captures', '*')):
                for dso in glob.glob(os.path.join(sesh, '*')):
                    if os.path.isdir(dso):
                        observations[dso] = get_metadata(dso, simple=True)

            # save
            with open(obspath, 'w') as f:
                json.dump(observations, f, indent=1)


        except Exception as e:
            print('Problem rebuilding previous observations ({:})'.format(e))
            sys.exit()

    # write critical kivy preferences
    from kivy.config import Config
    from jocular.jocular import Jocular

    Config.set('kivy', 'log_level', log)
    Config.set('kivy', 'keyboard_mode', 'system')
    Config.set('kivy', 'log_enable', 0)
    Config.set('kivy', 'exit_on_escape', '0')
    Config.set('graphics', 'position', 'auto')
    Config.set('graphics', 'fullscreen', 0)
    Config.set('graphics', 'borderless', 0)
    Config.set('postproc', 'double_tap_time', 250)
    Config.set('input', 'mouse', 'mouse,multitouch_on_demand')
    Config.write()

    # finally we can start app
    try:
        Jocular().run()
    except Exception as e:
        print('Jocular failed with error {:}'.format(e))
        sys.exit()
