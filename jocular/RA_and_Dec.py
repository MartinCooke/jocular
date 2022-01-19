''' Support for RA/Dec text representations and conversions.
'''
import math
from loguru import logger

class RA(float):
    def __new__(cls, ra):
        if type(ra) == str:
            try:
                h, m ,s = ra.split()
                if h[-1] == 'h':
                    h = h[:-1]
                ra = float(h)*15 + float(m)/4 + float(s)/240
                if (ra < 0) | (ra > 360):
                    return float('nan')
            except:
                return float('nan')
        return float.__new__(cls, ra)
 
    def __str__(self):
        if math.isnan(self):
            return ''
        hr, rest = divmod(self, 15)
        minit, rest = divmod(rest*4, 1)
        return "{:02d}h {:02d} {:02.0f}".format(int(hr), int(minit), rest*60)

    @classmethod
    def parse(cls, s):
        ''' We allow forms such as 23h34 21, 23 34 21, 23h34'21"
        '''
        try:
            s = s.replace('h', ' ').replace('"',' ').replace("'", ' ')
            parts = s.split()
            if len(parts) == 3:
                hrs, mins, secs = parts
                hrs = int(hrs)
                mins = int(mins)
                secs = float(secs)
                if (hrs >= 0) & (hrs < 24) & (mins >=0) & (mins < 60) & (secs >= 0) & (secs < 60):
                    return float(hrs*15 + mins/4 + secs/240 )
            return None
        except Exception as e:
            logger.warning('Problem parsing RA {:} ({:})'.format(s, e))
            return None


class Dec(float):
    def __new__(cls, dec):
        if type(dec) == str:
            try:
                d, m, s = dec.split()
                if d[-1] == '\u00b0':
                    d = d[:-1]
                if d[0] == '-':
                    dec = float(d) - float(m)/60 - float(s)/3600
                else:
                    dec = float(d) + float(m)/60 + float(s)/3600
                if (dec < -90) | (dec > 90):
                    return float('nan')
            except:
                return float('nan')
        return float.__new__(cls, dec)

    def __str__(self):
        if math.isnan(self):
            return ''
        if self >= 0:
            dd, rest = divmod(self, 1)
            dmin, rest = divmod(rest*60, 1)
            return "+{:d}\u00b0 {:02d} {:02.0f}".format(int(dd), int(dmin), rest*60)
        else:
            dd, rest = divmod(-self, 1)
            dmin, rest = divmod(rest*60, 1)
            return "-{:d}\u00b0 {:02d} {:02.0f}".format(int(dd), int(dmin), rest*60)

    @classmethod
    def parse(cls, s):
        ''' We allow forms such as 23d34 21, 23 34 21, 23<degree symbol>34'21.3"
        '''
        try:
            s = s.replace('d', ' ').replace('"',' ').replace("'", ' ').replace('\u00b0', ' ')
            parts = s.split()
            if len(parts) == 3:
                degs, mins, secs = parts
                degs = int(degs)
                mins = int(mins)
                secs = float(secs)
                if (degs >= -90) & (degs < 90) & (mins >=0) & (mins < 60) & (secs >= 0) & (secs <= 60):
                    if degs >= 0:
                        return float(degs + mins/60 + secs/3600)
                    return float(degs - mins/60 - secs/3600)
            return None
        except Exception as e:
            logger.warning('Problem parsing Dec {:} ({:})'.format(s, e))
            return None

