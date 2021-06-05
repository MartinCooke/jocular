import os


def connect_to_ASCOM_device(device_type=None, driver=None):
	''' Try to connect to ASCOM device; if driver is None, bring up chooser.
		Return dictionary containing some or all of driver, status, device and exception
	'''

	if os.name != 'nt':
		return {
			'status': 'ASCOM only works on Windows',
			'connected': False}

	try:
		import win32com.client
	except Exception as e:
		return {
			'status': 'Cannot import win30com.client; is ASCOM installed?',
			'connected': False,
			'exception': e
			}

	# try to connect to driver supplied
	if driver is not None:
		try:
			device = win32com.client.Dispatch(driver)
			device.Connected = True
			return {
				'device': device,
				'status': 'Connected to {:}'.format(device.Name),
				'connected': True
				}
		except:
			pass # we'll give user a chance to choose

	# need a device type for chooser
	if device_type is None:
		return {
			'status': 'You must specify a device type',
			'connected': False
			}

	# chooser
	try:
		chooser = win32com.client.Dispatch("ASCOM.Utilities.Chooser")
		chooser.DeviceType = device_type
		driver = chooser.Choose(None)
	except Exception as e:
		return {
			'status': 'Unable to choose driver',
			'exception': e,
			'connected': False
			}

	# connect
	try:
		device = win32com.client.Dispatch(driver)
		device.Connected = True
		return {
			'device': device, 
			'driver': driver, 
			'status': 'Connected to {:}'.format(device.Name),
			'connected': True
			}
	except Exception as e:
		return {
			'status': 'Unable to connect to {:}'.format(driver),
			'exception': e,
			'connected': False
			}

