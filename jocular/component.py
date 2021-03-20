''' Manages all individual components, including imports/instantiation,
    in a uniform way. A bit 'meta' but some advantages of doing it this
    way.
'''

import time
import importlib
import math
from collections import OrderedDict
from kivy.app import App
from kivy.logger import Logger
from kivy.event import EventDispatcher
from kivy.properties import StringProperty, NumericProperty, BooleanProperty
from jocular.widgets import jicon

def remove_nulls_from_dict(d):
    return {k: v for k, v in d.items() \
        if not((v is None) or \
            (isinstance(v, str) and v.strip() == '') or  \
            (isinstance(v, float) and math.isnan(v)) or  \
            (isinstance(v, dict) and len(v) == 0) or \
            (isinstance(v, list) and len(v) == 0))}

class Component(EventDispatcher):

    components = OrderedDict()
    infoline = StringProperty('')   # ensures each component can signal its status for technical panel
    errors = NumericProperty(0)     # use these at some point
    warnings = NumericProperty(0)
    changed = BooleanProperty(True)

    @classmethod
    def get(cls, name):
        # Returns component whose class is identified by name; loads if not found

        if name in cls.components:
            return cls.components[name]
        try:
            t0 = time.time()
            module = importlib.import_module('jocular.' + name.lower())
            class_ = getattr(module, name)
            import_time = time.time() - t0
            t1 = time.time()
            inst = class_()
            init_time = time.time() - t1
            cls.register(inst)
            Logger.info('Component: imported {:} in {:.0f}ms, init in {:.0f}ms'.format(name, 
                1000 * import_time, 1000 * init_time))
            return inst
        except Exception as e:
            Logger.error('Component: cannot import module {:} ({:})'.format(name, e))
            return
 
    @classmethod
    def is_loaded(cls, name):
        return name in cls.components

    @classmethod
    def register(cls, obj):
        name = obj.__class__.__name__
        if name not in cls.components:
            cls.components[name] = obj
            App.get_running_app().gui.initialise_component(name)
        else:
            Logger.error('Component: name clash for {:}'.format(name))
 
    @classmethod
    def initialise_new_object(cls):
        for c in cls.components.keys():
            cls.components[c].changed = False
            cls.components[c].on_new_object()

    @classmethod
    def save_object(cls):
        for c in cls.components.keys():
            cls.components[c].on_save_object()

    @classmethod
    def close(cls):
        Logger.info('Component: closedown')
        for c in cls.components.keys():
            cls.components[c].on_close()

    @classmethod
    def bind_status(cls):
        for name, inst in cls.components.items():
            cls.get('Status').bind_status(name, inst)
            inst.info('loaded')

    @classmethod
    def check_change(cls):
        for c in cls.components.keys():
            if cls.components[c].changed:
                App.get_running_app().gui.something_has_changed = True
                return
        App.get_running_app().gui.something_has_changed = False

    def redraw(self, *args): pass
    def on_new_object(self, *args): pass
    def on_save_object(self, *args): pass
    def on_close(self, *args): pass

    def on_changed(self, *args):
        Component.check_change()

    def info(self, message=None, prefix=None, typ='normal'):
        i = '' if typ == 'normal' else jicon(typ)
        self.infoline = '{:}: [b]{:}[/b] {:}'.format(message, self.__class__.__name__, i)

    def warn(self, message):
        self.warnings += 1
        self.info(message, typ='warn')
        Logger.debug('{:}: {:}'.format(self.__class__.__name__, message))

    def error(self, message):
        self.errors += 1
        self.info(message, typ='error')
        Logger.exception('{:}: {:}'.format(self.__class__.__name__, message))

