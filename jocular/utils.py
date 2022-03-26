''' Miscellany
'''

import os
import numpy as np
import math
import shutil
from scipy.stats import trimboth
from loguru import logger 
from pathlib import Path
from kivymd.toast.kivytoast import toast as mdtoast

def is_null(v):
    return (v is None) or \
        (isinstance(v, str) and v.strip() == '') or  \
        (isinstance(v, float) and math.isnan(v)) or  \
        (isinstance(v, dict) and len(v) == 0) or \
        (isinstance(v, list) and len(v) == 0)

def toast(mesg, duration=1):
    mdtoast(mesg, duration=duration)
    logger.info('toast: {:}'.format(mesg))

def angle360(angle):
    if angle < 0:
        return angle + 360
    elif angle > 360:
        return angle - 360
    else:
        return angle

def percentile_clip(a, perc=80):
    return np.mean(trimboth(np.sort(a, axis=0), (100 - perc)/100, axis=0), axis=0)    

def unique_member(l):
    # if list has a single unique member, return it, otherwise None
    if len(set(l)) == 1:
        return l[0]
    else:
        return None

def get_datadir():
    ''' Read datadir name from .jocular in home; if .jocular doesn't exist,
        or if the datadir doesn't exist, caller will deal with it
    '''
    try:
        with open(os.path.join(str(Path.home()), '.jocular'), 'r') as f:
            datadir = f.read().strip()
        if os.path.exists(datadir):
            return datadir
        return None
    except:
        return None

def add_if_not_exists(path):
    if not os.path.exists(path):
        try:
            os.mkdir(path)
        except FileExistsError:
            raise FileExistsError

def start_logging(path):
    ''' start logging on given path
    '''

    logger.remove()
    fmt = "{time: DMMMYY HH:mm:ss.SSS} | {level: <8} | {name: <25} | {function: <26} | {line: >4} | {message}"
    logger.add(os.path.join(path, 'jocular.log'), mode='a', format=fmt, level='TRACE',
        rotation='1MB', retention=20)
    for i in range(10):
        logger.info('')
    logger.info('--------------------------')
    logger.info('Started logging')
    logger.info('')

def make_unique_filename(path):
    if not os.path.exists(path):
        return path
    root, name = os.path.split(path) 
    base, ext = os.path.splitext(name)
    cnt = 1
    while os.path.exists(os.path.join(root, '{:}_{:}{:}'.format(base, cnt, ext))):
        cnt += 1
    return os.path.join(os.path.join(root, '{:}_{:}{:}'.format(base, cnt, ext)))

def purify_name(nm):
    # replace any chars that could cause problems with filesystem by spaces
    return nm.replace(':',' ').replace('/',' ').replace('\\',' ').strip()

# consider combining with above; called in ObjectIO
def generate_observation_name(path, prefix=None):

    # use names of form obs 1, obs 2 if prefix is obs
    if (prefix is None) or (prefix == 'light') or (len(prefix) == 0):
        n = 1
        while os.path.exists(os.path.join(path, 'obs {:}'.format(n))):
            n += 1
        return 'obs {:}'.format(n)

    # otherwise using name is possible
    if not os.path.exists(os.path.join(path, prefix)):
        return prefix

    # otherwise add a version number
    n = 1
    while os.path.exists(os.path.join(path, '{:} v{:}'.format(prefix, n))):
        n += 1
    return '{:} v{:}'.format(prefix, n)

def s_to_minsec(s):
    if s < 1:
        return '{:.0f}ms'.format(1000 * s)
    mins, secs = divmod(round(s), 60)
    if mins == 0:
        return '{:}s'.format(secs)
    elif secs == 0:
        return '{:}m'.format(mins)
    else:
        return '{:d}m{:d}s'.format(mins, secs)

def move_to_dir(frompath, topath):
    ''' move from frompath to topath, making topath dir and 
        creating unique name if necessary
    '''

    try:
        toparent, tobase = os.path.split(topath)
        fromparent, filename = os.path.split(frompath)

        # empty parent implies use fromparent
        if not toparent:
            # treat as subdirectory of from
            topath = os.path.join(fromparent, tobase)
        add_if_not_exists(topath)

        # create unique filename
        dest = make_unique_filename(os.path.join(topath, filename))

        # instead of this
        # os.rename(frompath, dest)    
        # use this to handle case of moving from one filesys to another
        shutil.move(frompath, dest)    

    except Exception as e:
        logger.exception('problem moving {:} to {:} ({:})'.format(frompath, topath, e))


