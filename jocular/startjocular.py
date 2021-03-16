''' Initiates jocular, checking if we have a data directory
'''

import os
import sys
import click
from datetime import datetime
from pathlib import Path


def get_datadir():
    try:
        with open(os.path.join(str(Path.home()), '.jocular'), 'r') as f:
            return f.read().strip()
    except:
        return None


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
def startjocular(datadir, log):

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

    # stop Kivy from interpreting any args
    os.environ["KIVY_NO_ARGS"] = "1"

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
