''' Filterwheel: represents collection of filters available as well 
    as providing control of an electronic filter wheel (EFW) where 
    available. All the individual filter information should reside 
    here e.g. on-screen colour representations, transmissibilities 
    if needed for ordering taking multiple flats.

    Currently supports (hard-coded) the SX USB filter wheel only.
'''

# import hid   # human interface device, to allow access to SX EFW
from kivy.app import App
from kivy.logger import Logger
from kivy.clock import Clock
from kivy.properties import StringProperty
from jocular.component import Component
from jocular.widgets import JPopup


class FilterWheel(Component):

    filter_properties = {
        "L": {"color": (0.7, 0.7, 0.7), "bg_color": (0.1, 0.1, 0.1, 0.5)},
        "R": {"color": (1, 0, 0), "bg_color": (1, 0, 0, 0.6)},
        "G": {"color": (0, 1, 0), "bg_color": (0, 1, 0, 0.5)},
        "B": {"color": (0, 0, 1), "bg_color": (0, 0, 1, 0.5)},
        "dark": {"color": (0.1, 0.1, 0.1), "bg_color": (0, 0, 0, 0)},
        "Ha": {"color": (0.8, 0.3, 0.3), "bg_color": (1, 0.6, 0.6, 0.5)},
        "OIII": {"color": (0.2, 0.6, 0.8), "bg_color": (0, 0, 0, 0)},
        "SII": {"color": (0.1, 0.8, 0.4), "bg_color": (0, 0, 0, 0)},
        "spec": {"color": (0.7, 0.6, 0.2), "bg_color": (0, 0, 0, 0)},
        "-": {"color": (0.3, 0.3, 0.3), "bg_color": (0, 0, 0, 0)},
    }

    current_filter = StringProperty("L")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # form array of filters
        config = App.get_running_app().config
        self.filters = [
            config.get("Filters", "filter{:}".format(i + 1)) for i in range(9)
        ]

    def on_new_object(self):
        self.connected = False
        self.connect()
        if self.connected:
            self.info("connected")
        else:
            self.info("not connected")

    def on_current_filter(self, *args):
        App.get_running_app().gui.set("filter_button", self.current_filter)
        self.info("{:} filter".format(self.current_filter))

    def update_filter(self, fnum, ftype):
        # called when config changes in jocular itself
        if fnum.startswith("filter"):
            findex = int(fnum[6:]) - 1
            self.filters[findex] = ftype

    # methods for other components to access things like filter colours
    def get_color(self, name="L"):
        if name in self.filter_properties:
            return self.filter_properties[name]["color"]
        else:
            # mid-grey
            if name != "empty":
                self.warn("no filter called {:}".format(name))
            return 0.5, 0.5, 0.5, 1

    def on_close(self):
        if self.connected and self.efw:
            self.efw.close()

    def connect(self):
        # Try to connect

        if self.connected:
            return

        self.connected = False

        try:
            import hid
        except Exception as e:
            Logger.warn("FilterWheel: cannot import HID ({:})".format(e))
            return
        try:
            if hasattr(self, "efw"):
                if self.efw:
                    self.efw.close()
            else:
                self.efw = hid.device()
        except Exception as e:
            Logger.warn("FilterWheel: failed to get HID device ({:})".format(e))
            return

        # note that if we open when already open, it fails
        try:
            self.efw.open(0x1278, 0x0920)
            self.connected = True
            Logger.info("FilterWheel: connected!")
        except Exception as e:
            Logger.trace("FilterWheel: failed to open device ({:})".format(e))
            self.connected = False

    def order_by_transmission(self, filts):
        #  need to add others to this and perhaps do it via filter_properties
        if type(filts) != list:
            filts = [filts]
        t_order = ["Ha", "B", "G", "R", "L"]
        return [f for f in t_order if f in filts]

    #  since filter change takes some seconds, we use callbacks to control actions
    #  once the filterwheel is in position; in simple cases where there are no filters
    #  or user is requesting same filter, no need for callbacks -- up to the caller

    def select_filter(self, name="L", changed_action=None, not_changed_action=None):
        """Connect to filter by name if possible, calling appropriate callback if provided"""

        Logger.info("FilterWheel: select filter {:}".format(name))

        # no change of filter so execute callback if it exists, or return otherwise
        if self.current_filter == name:
            if changed_action is not None:
                changed_action()
            return

        # we need to change filter: does the filter exist?
        if (name not in {"dark", "L"}) and name not in self.filters:
            self.warn("Cannot find filter {:}".format(name))
            if not_changed_action is not None:
                not_changed_action()
            return

        # if we have a filterwheel, then execute the change
        if self.connected:
            position = self.filters.index(name) + 1  # 1-indexed
            try:
                self.efw.write([position + 128, 0])
                if changed_action is not None:
                    Clock.schedule_once(changed_action, 3)
                self.current_filter = name
            except Exception as e:
                Logger.error(
                    "FilterWheel: exception moving filterwheel ({:})".format(e)
                )
                self.warn("problem moving EFW")
                if not_changed_action is not None:
                    not_changed_action()
        # prompt user
        else:
            if name == "dark":
                title = "Cap scope for darks"
            else:
                title = "Change filter to {:}".format(name)
            self.current_filter = name
            JPopup(title=title, actions={"Done": changed_action}).open()
