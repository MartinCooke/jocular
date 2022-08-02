''' Filterwheel device family
'''

from functools import partial
from loguru import logger

from kivy.clock import Clock
from kivy.properties import StringProperty
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog

from jocular.component import Component
from jocular.device import DeviceFamily, Device
from jocular.ascom import connect_to_ASCOM_device
from jocular.utils import toast


class FilterWheel(Component, DeviceFamily):

    modes = {
        'Single': 'SingleFW',
        'Manual': 'ManualFW', 
        'SX EFW': 'SXFW',
        'ASCOM': 'ASCOMFW'
    }

    default_mode = 'Single'
    family = 'FilterWheel'

    current_filter = StringProperty('L')


    def get_state(self):
        return {
            'current_filter': self.current_filter,
            'filtermap': self.filtermap()}


    def filtermap(self):
        # create map from filtername to position e.g. {'L': 1, 'R': 2}
        if self.device is None:
            return {}
        return {getattr(self.device, f'f{p}'): p for p in range(1, 10)}


    def select_filter(self, name='L', changed_action=None, not_changed_action=None):

        logger.debug(f'trying to change to filter {name}')
        self.changed_action = changed_action
        self.not_changed_action = not_changed_action

        # no change of filter
        if self.current_filter == name:
            logger.debug(f'no need to change filter {name}')
            changed_action()
            return

        # filter not in wheel
        if name not in self.filtermap():
            # if we want dark or we currently have dark, special case
            if name == 'dark' or self.current_filter == 'dark':
                if name == 'dark':
                    title = 'Is scope capped for darks?'
                else:
                    title = 'Is scope uncapped for lights?'
                self.dialog = MDDialog(
                    auto_dismiss=False,
                    text=title,
                    buttons=[
                        MDFlatButton(text="DONE", 
                            text_color=self.app.theme_cls.primary_color,
                            on_press=partial(self.confirmed_fw_changed, name)),
                        MDFlatButton(
                            text="CANCEL", 
                            text_color=self.app.theme_cls.primary_color,
                            on_press=self.confirmed_fw_not_changed)
                    ],
                )
                self.dialog.open()

            else:
                toast(f'Cannot find filter {name}')
                logger.warning(f'Cannot find filter {name} in current filterwheel')
                if not_changed_action is not None:
                    not_changed_action()
        else:
            # if we get here, we can go ahead
            self.change_filter(name)


    def confirmed_fw_changed(self, name, *args):
        self.dialog.dismiss()
        self.fw_changed(name)


    def confirmed_fw_not_changed(self, *args):
        self.dialog.dismiss()
        self.fw_not_changed()


    def change_filter(self, name, *args):
        try:
            self.device.select_position(
                position=self.filtermap()[name], 
                name=name, 
                success_action=partial(self.fw_changed, name),
                failure_action=self.fw_not_changed)
        except Exception as e:
            toast(f'problem moving EFW ({e})')
            if self.not_changed_action is not None:
                self.not_changed_action()
            return


    def fw_changed(self, name, dt=None):
        # change has been done
        self.current_filter = name
        logger.debug(f'Filter changed to {name}')
        if self.changed_action is not None:
            self.changed_action()


    def fw_not_changed(self):
        logger.debug('Filter not changed')
        if self.not_changed_action is not None:
            self.not_changed_action()


    def device_connected(self):
        # called by DeviceFamily when a device connects
        if not hasattr(self, 'device'):
            return False

        if self.device is not None:
            self.device.settings_have_changed()


class GenericFW(Device):

    family = StringProperty('FilterWheel')

    f1 = StringProperty('-')
    f2 = StringProperty('-')
    f3 = StringProperty('-')
    f4 = StringProperty('-')
    f5 = StringProperty('-')
    f6 = StringProperty('-')
    f7 = StringProperty('-')
    f8 = StringProperty('-')
    f9 = StringProperty('-')


    def __init__(self, **args):
        ftypes = Component.get('FilterChooser').get_filter_types()
        self.configurables = [('f' + str(i), {'name': 'position ' + str(i), 'options': ftypes}) for i in range(1, 10)]
        super().__init__(**args)


    def settings_have_changed(self):
        
        # only transmit changes for connected devices
        if not self.connected:
            return
        
        ftypes = Component.get('FilterChooser').get_filter_types()

        # remove duplicates and non-existent filters
        logger.debug('Checking for and removing duplicate and non-existent filters')
        filts = set({})
        for pos in range(1, 10):
            fname = f'f{pos}'
            f = getattr(self, fname)
            if f not in ftypes:
                setattr(self, fname, '-')
            if f in filts:
                setattr(self, fname, '-')
            else:
                filts.add(f)
        Component.get('CaptureScript').filterwheel_changed()


class SingleFW(GenericFW):


    def connect(self):
        self.connected = True
        self.status = 'Single filter connected'


    def select_position(self, position=None, name=None, success_action=None, failure_action=None):
        if success_action is not None:
            success_action()


# class SimulatorFW(GenericFW):

#   def select_position(self, position=None, name=None, success_action=None, failure_action=None):
#       if success_action is not None:
#           success_action()

#   def connect(self):
#       self.connected = True
#       self.status = 'Filterwheel simulator active'


class ManualFW(GenericFW):

    def connect(self):
        self.connected = True
        self.status = 'Manual filterwheel'


    def select_position(self, position=None, name=None, success_action=None, failure_action=None):
        self.dialog = MDDialog(
            auto_dismiss=False,
            text=f'Change filter to {name} in position {position}',
            buttons=[
                MDFlatButton(text="DONE", 
                    text_color=self.app.theme_cls.primary_color,
                    on_press=partial(self.post_dialog, success_action)),
                MDFlatButton(
                    text="CANCEL", 
                    text_color=self.app.theme_cls.primary_color,
                    on_press=partial(self.post_dialog, failure_action))
            ],
        )
        self.dialog.open()


    def post_dialog(self, action, *args):
        ''' close dialog and perform action (i.e. success or failure to change)
        '''
        self.dialog.dismiss()
        if action is not None:
            action()


class SXFW(GenericFW):

    def connect(self):

        if self.connected:
            return

        self.connected = False
        logger.debug('importing HID')
        try:
            import hid
        except Exception as e:
            logger.warning(f'Cannot import HID ({e})')
            self.status = 'Cannot import HID'
            return

        try:
            if hasattr(self, 'fw'):
                if self.fw:
                    logger.debug('closing filterwheel')
                    self.fw.close()
            else:
                self.fw = hid.device()
                logger.debug('got HID device')

        except Exception as e:
            logger.warning(f'Failed to get HID ({e})')
            self.status = 'Failed to get HID device'
            return

        # note that if we open when already open, it fails
        try:
            logger.debug('opening SX EFW')
            self.fw.open(0x1278, 0x0920)
            self.connected = True
            self.status = 'SX filterwheel connected'
            logger.debug('successful')
        except Exception as e:
            logger.warning(f'fw.open failed ({e})')
            self.status = 'fw.open failed'
            self.connected = False


    def select_position(self, position=None, name=None, success_action=None, failure_action=None):
        try:
            # move SX filterwheel
            logger.debug(f'Moving SX EFW to position {position}')
            self.fw.write([position + 128, 0])
            # wait three seconds before informing controller it has been done
            logger.debug(f'success so setting up action {success_action}')
            Clock.schedule_once(success_action, 3)
        except Exception as e:
            logger.debug(f'failed to select position ({e})')
            # controller will handle this further
            if failure_action is not None:
                failure_action()


class ASCOMFW(GenericFW):

    driver = StringProperty(None)


    def disconnect(self):
        logger.debug('closing ASCOM filterwheel')
        self.fw.Connected = False


    def connect(self):

        if self.connected:
            return

        res = connect_to_ASCOM_device(device_type='FilterWheel', driver=self.driver)
        self.connected = res.get('connected', False)
        self.status = res['status']
        if self.connected:
            self.driver = res.get('driver', self.driver)
            self.fw = res['device']
        else:
            if 'exception' in res:
                self.status += " ({res['exception']})"


    def select_position(self, position=None, name=None, success_action=None, failure_action=None):
        try:
            # possible 0-indexed?
            position = position - 1
            # move filterwheel
            logger.debug(f'Moving ASCOM EFW to position {position}')
            self.fw.Position = position
            # wait three seconds before informing controller it has been done
            logger.debug(f'success so setting up action {success_action}')
            Clock.schedule_once(success_action, 3)
        except:
            # controller will handle this
            if failure_action is not None:
                failure_action()

