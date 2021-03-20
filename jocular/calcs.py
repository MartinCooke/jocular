''' Various astro calcs mainly based on Meuss. 
'''

import numpy as np
import math
import time
from datetime import datetime

def julian_date(when):
	# from Meuss p 61; 'when' is a datetime object

	y = when.year
	m = when.month
	d = when.day + when.hour/24 + when.minute/(24*60) + when.second/(24*3600)

	if m < 3:
		y -= 1
		m += 12

	a = int(y / 100)

	if y >= 1582 and m >= 10:
		# Gregorian
		a = int(y/100)
		b = 2 - a + int(a / 4)
	else: 
		# Julian
		b = 0

	jd = int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5
	return jd


def to_range(x, d):
	# reduce x to range 0-d by adding or subtracting multiples of d
	if x < 0:
		return x - int((x / d) - 1) * d
	else:
		return x - int((x / d)) * d

def local_sidereal_time(when, longitude):
	# direct method of Meuss p87

	# when must be in UT
	jd = julian_date(when)
	t = (jd - 2451545.0) / 36525.0
	mst = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + .000387933 * t**2 - t**3 / 38710000

	# convert to 0-360
	mst = to_range(mst, 360)

	# convert from Greenwich to local
	lst = mst + longitude

	return lst

def sun_altitude(when, latitude, longitude):
	# Meuss p163+

	jd = julian_date(when)
	rads = math.pi / 180.


	t = (jd - 2451545.0) / 36525.0
	L0 = 280.46646 + 36000.76983 * t + 0.0003032 * t * t
	L0 = to_range(L0, 360)
	M = 357.52911 + 35999.05029 * t - 0.0001537 * t * t
	#e = 0.016708634 - 0.000042037 * t - 0.0000001267 * t * t
	C = (1.914602 - 0.004817 * t - 0.000014 * t * t) * np.sin(M * rads) + \
		(0.019993 - 0.000101 * t) * np.sin(2 * M * rads) + \
		0.000289 * np.sin(3 * M * rads)
	long_sun = L0 + C
	#v = M + C
	# R = (1.000001018 * (1 - e * e)) / (1 + e * np.cos(v * rads))
	sigma = 125.04 - 1934.136 * t
	lam = long_sun - 0.00569 - 0.00478 * np.sin(sigma * rads)
	ep = 23 + (26/60) + (21.448/3600) - (46.815*t + 0.00059 * t**2 - 0.001813*t**3) / 3600
	ep_corr = ep + 0.00256 * np.cos(sigma * rads)
	ra = np.arctan2(np.cos(ep_corr * rads) * np.sin(lam * rads), np.cos(lam * rads)) / rads
	ra = to_range(ra, 360)
	dec = np.arcsin(np.sin(ep_corr * rads) * np.sin(lam * rads)) / rads

	# now convert to locale

	ts = time.time()
	utc_offset = (datetime.fromtimestamp(ts) - datetime.utcfromtimestamp(ts)).total_seconds() / 3600.0
	lst = local_sidereal_time(when, longitude)
	lat = latitude * rads
	H = (-utc_offset*15 + lst - ra) * rads
	alt = np.arcsin(np.sin(lat) * np.sin(dec * rads) + np.cos(lat) * np.cos(dec * rads) * np.cos(H)) / rads

	return alt

