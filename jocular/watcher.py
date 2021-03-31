''' Monitors any incoming subs
'''

import os
import numpy as np

from kivy.logger import Logger
from kivy.app import App
from kivy.clock import Clock
from kivy.properties import ConfigParserProperty

from skimage.transform import rescale, downscale_local_mean

from jocular.component import Component
from jocular.utils import move_to_dir
from jocular.image import Image, ImageNotReadyException, is_fit, save_image

def debayer(im, pattern=None, method=None):
    ''' Note that there is a bug in the Linux version of colour_demosaicing or
        one of its dependencies so we'll import here for now to allow Linux
        users to at least operate in Mono 
    '''
    from colour_demosaicing import (
        demosaicing_CFA_Bayer_bilinear,
        demosaicing_CFA_Bayer_Malvar2004,
        demosaicing_CFA_Bayer_Menon2007
    )
    meths = {
        'bilinear': demosaicing_CFA_Bayer_bilinear,
        'Malvar2004': demosaicing_CFA_Bayer_Malvar2004,
        'Menon2007': demosaicing_CFA_Bayer_Menon2007,
    }
    deb = meths[method](im, pattern=pattern)

    # rescale to original intensity range
    cfa_min, cfa_max = np.min(im), np.max(im)
    deb_min, deb_max = np.min(deb), np.max(deb)
    deb = cfa_min + (cfa_max - cfa_min) * (deb - deb_min) / (deb_max - deb_min)

    ''' might eventually want to support CMYK conversion eg for Lodestar C
        R = 255 × (1-C) × (1-K)
        G = 255 × (1-M) × (1-K)
        B = 255 × (1-Y) × (1-K)
    '''

    return deb

def binning(im, binfac, binmethod='interpolation'):
    binfac = int(binfac)
    if binfac < 2:
        return im
    if binmethod == 'interpolatation':
        return rescale(im, 1 / binfac, anti_aliasing=True, mode='constant', 
            preserve_range=True, multichannel=False)
    return downscale_local_mean(im, (binfac, binfac))


class Watcher(Component):

    # new in v0.5
    bayerpattern = ConfigParserProperty('mono', 'Watcher', 'bayerpattern', 'app', val_type=str)
    bayermethod = ConfigParserProperty('bilinear', 'Watcher', 'bayermethod', 'app', val_type=str)
    binfac_on_input = ConfigParserProperty(1, 'Watcher', 'binfac_on_input', 'app', val_type=int)
    binmethod = ConfigParserProperty('interpolate', 'Watcher', 'binmethod', 'app', val_type=str)

    def __init__(self):
        super(Watcher, self).__init__()
        self.watched_dir = App.get_running_app().get_path('watched')
        self.watching_event = Clock.schedule_interval(self.watch, .3)

    def on_new_object(self):
        self.flush()

    def on_close(self):
        self.watching_event.cancel()
        self.flush()    # user has had enough so move any FITs to delete

    def flush(self):
        # move any FITs that are not masters to a 'unused' folder in watcher
        # (masters are saved immediately before new object, so risk they are not spotted in time!)
        for f in os.listdir(self.watched_dir):
            if is_fit(f):
                if not f.startswith('master'):
                    move_to_dir(os.path.join(self.watched_dir, f), 'unused')

    def get_possible_fits(self):
        fits = [os.path.join(self.watched_dir, d) for d in os.listdir(self.watched_dir)]
        # for ASIlive look deeper
        asipath = os.path.join(self.watched_dir, 'ASILive_AutoSave', 'SingleFrame')
        if os.path.exists(asipath):
            for sdir in os.listdir(asipath):
                pth = os.path.join(asipath, sdir)
                if os.path.isdir(pth):
                    fits += [os.path.join(pth, d) for d in os.listdir(pth)]
        # print('possible fits', fits)
        return fits

    def watch(self, dt):
        '''Watcher handles two types of event:

            1.  Users drop individual subs (manually or via a capture program); if
                validated these are passed to ObjectIO
            2.  Users drop master calibration frames; if validated, passed to Calibrator
                to become part of the library and become available for immediate use

            Validated files are removed from 'watched'. If not validated, files are
            either left to be re-handled on the next event cycle, or moved to 'invalid'.
            Non-fits files are moved to 'ignored'
         '''

        for path in self.get_possible_fits():
            f = os.path.basename(path)

        # for f in os.listdir(self.watched_dir):
        #     path = os.path.join(os.path.join(self.watched_dir, f))
            if is_fit(f):
                try:
                    s = Image(path, check_image_data=True)

                    ''' New in v0.5
                        Check if this is a jocular sub or not. If not and user
                        wants to bin or debayer or both, do this, creating new
                        Jocular FITs, write them to watched dir so they
                        are loaded, and save original FITs 
                    '''

                    if not s.created_by_jocular and (self.bayerpattern != 'mono' or self.binfac_on_input > 1):
                        bn = os.path.basename(path)
                        im = s.get_image()
                        if self.bayerpattern != 'mono' and not s.is_master:
                            rgb = debayer(im, pattern=self.bayerpattern, method=self.bayermethod)
                            Logger.info('Watcher: debayered')
                            for i, chan in enumerate(['R', 'G', 'B']):
                                self.save_sub_to_watched(s, rgb[:, :, i], bn, filt=chan)
                        else:
                            self.save_sub_to_watched(s, im, bn, filt=None)

                        Component.get('ObjectIO').new_aliensub_from_watcher(path)

                    elif s.is_master:
                        Component.get('Calibrator').new_master_from_watcher(s)

                    else:
                        Component.get('ObjectIO').new_sub_from_watcher(s)

                except ImageNotReadyException as e:
                    # give it another chance on next event cycle
                    Logger.debug('Watcher: image not ready {:} ({:})'.format(f, e))
                except Exception as e:
                    # irrecoverable, so move to invalid, adding timestamp
                    Logger.debug('Watcher: other issue {:} ({:})'.format(f, e))
                    move_to_dir(path, 'invalid')

            elif not os.path.isdir(path):
                move_to_dir(path, 'ignored')


    def save_sub_to_watched(self, sub, im, nm, filt=None):
        ''' Save debayered or binned image, constructing details from Image instance
        '''

        if self.binfac_on_input > 1:
            im = binning(im, self.binfac_on_input, binmethod=self.binmethod)
            Logger.info('Watcher: binning by factor {:} down to  {:} x {:}'.format(
                self.binfac_on_input, im.shape[1], im.shape[0]))

        filt=sub.filter if filt is None else filt

        save_image(data=im.astype(np.uint16), 
            path=os.path.join(self.watched_dir, '{:}_{:}'.format(filt, nm)),
            filt=filt,
            sub_type=sub.sub_type,
            exposure=sub.exposure,
            temperature=sub.temperature
            )
