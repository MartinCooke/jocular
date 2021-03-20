''' Support for RA/Dec text representations and conversions.
'''

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
        hr, rest = divmod(self, 15)
        minit, rest = divmod(rest*4, 1)
        return "{:02d}h {:02d} {:02.0f}".format(int(hr), int(minit), rest*60)

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
        if self >= 0:
            dd, rest = divmod(self, 1)
            dmin, rest = divmod(rest*60, 1)
            return "+{:d}\u00b0 {:02d} {:02.0f}".format(int(dd), int(dmin), rest*60)
        else:
            dd, rest = divmod(-self, 1)
            dmin, rest = divmod(rest*60, 1)
            return "-{:d}\u00b0 {:02d} {:02.0f}".format(int(dd), int(dmin), rest*60)

