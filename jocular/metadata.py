''' Handle info.json in its various instantiations over the different versions
'''

import os
import json
from datetime import datetime
from loguru import logger

from jocular.image import fits_in_dir, update_fits_header
from jocular.component import Component
# from jocular.image import Image, ImageNotReadyException, is_fit


def remove_empties(d):
    return {
        k: v
        for k, v in d.items()
        if not ((v == '') or (v is None) or (v == {}) or (v == []))
    }


def get_metadata(path, simple=False):
    # Read metadata from path, constructing if necessary
    #  supports info.json (v1/2 of Jocular) and info3.json (v3)
    #  main difference is that info3 is simpler; will always read info3 in pref if both exist

    v1 = False
    try:
        # if we can find v3 metadata, load it
        with open(os.path.join(path, 'info3.json'), 'r') as f:
            md = json.load(f)
    except:
        try:
            #  if pre v3 metadata exists, load it
            with open(os.path.join(path, 'info.json'), 'r') as f:
                md = json.load(f)
            # convert
            newmd = {}
            for p in [
                'Name',
                'Con',
                'OT',
                'Notes',
                'session_notes',
                'SQM',
                'temperature',
                'rejected',
                'seeing',
                'transparency',
                'telescope',
                'camera',
                'exposure',
                'sub_type',
            ]:
                if p in md:
                    newmd[p] = md[p]
            if 'scope' in md and 'orientation' in md['scope']:
                newmd['orientation'] = md['scope']['orientation']
            md = newmd
            v1 = True
        except:
            # cannot find any metadata, so set to empty
            md = {}

    #  if no name, use name of directory contaiining FITs
    if 'Name' not in md:
        md['Name'] = os.path.basename(path)

    md = remove_empties(md)

    # create an infov3 for speed of later loading all obs
    if v1:
        try:
            with open(os.path.join(path, 'info3.json'), 'w') as f:
                json.dump(md, f, indent=1)
        except:
            pass

    #  compute session date/time and number of subs dynamically
    fits = fits_in_dir(path)
    md['nsubs'] = len(fits)
    if len(fits) > 0:
        md['session'] = datetime.fromtimestamp(os.path.getmtime(fits[0])).strftime(
            '%d %b %y %H:%M'
        )

    # convert SQM to sky_brightness now we are handling NELM
    if 'SQM' in md:
        md['sky_brightness'] = md['SQM']
        del md['SQM']

    # handle some legacy changes
    if 'OT' in md and 'Name' in md:
        nm = md['Name'].upper()
        if md['OT'].upper() == 'G+':
            if nm.startswith('ARP') or nm.startswith('VV') or nm.startswith('AM '):
                md['OT'] = 'PG'
            elif nm[:3] in {'HIC', 'PCG', 'SHK'}:
                md['OT'] = 'CG'

    # often we want metadata for observing list in simple format
    if simple:
        return { 
            'Name': md.get('Name', ''),
            'OT': md.get('OT', ''),
            'Con': md.get('Con', ''),
            'Session': md.get('session', ''),
            'N': md.get('nsubs', 0),
            'Notes': md.get('Notes', '')
            }

    return md

class Metadata(Component):

    def on_new_object(self):
        self.md = {}

    def on_previous_object(self):
        self.load(Component.get('ObjectIO').current_object_dir)

    def load(self, path):
        self.md = get_metadata(path)

    def save(self, path, change_fits_headers=False):
        # Save metadata to path in above format

        self.md = remove_empties(self.md)

        if 'Name' not in self.md:
            self.md['Name'] = os.path.basename(path)

        # we no longer want to save this information
        if 'rejected' in self.md:
            del self.md['rejected']
        if 'nsubs' in self.md:
            del self.md['nsubs']
        if 'session' in self.md:
            del self.md['session']

        try:
            with open(os.path.join(path, 'info3.json'), 'w') as f:
                json.dump(self.md, f, indent=1)
        except Exception as e:
            logger.warning('Problem saving info3.json to {:} ({:})'.format(path, e))

        # change FITs header if requested
        if change_fits_headers:
            logger.debug('Changing fits headers')
            for f in fits_in_dir(path):
                update_fits_header(f, 
                    exposure=self.md.get('exposure', None),
                    sub_type=self.md.get('sub_type', None),
                    temperature=self.md.get('temperature', None))

    def set(self, field, value=None):
        # set one or more fields of metadata
        if value is None and type(field) == dict:
            for f, v in field.items():
                self.md[f] = v
        else:
            self.md[field] = value

    def get(self, field, default=None):
        # get one or more fields of metadata
        if type(field) == list or type(field) == set:
            d = {}
            for f in field:
                if f in self.md:
                    d[f] = self.md[f]
            return d
        else:
            return self.md.get(field, default)

