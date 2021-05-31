''' Manages all individual components, including imports/instantiation,
    in a uniform way.
'''

import json
import importlib
import math
from loguru import logger
from collections import OrderedDict
from kivy.app import App
from kivy.event import EventDispatcher
from kivy.properties import StringProperty, ListProperty

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
    #errors = NumericProperty(0)     # use these at some point
    #warnings = NumericProperty(0)
    save_settings = ListProperty([])

    @classmethod
    def get(cls, name):
        # Returns component whose class is identified by name; loads if not found

        logger.trace(name)
        if name in cls.components:
            return cls.components[name]
        try:
            module = importlib.import_module('jocular.' + name.lower())
            class_ = getattr(module, name)
            inst = class_()
            cls.register(inst)
            logger.info('{:} imported'.format(name))
            return inst
        except Exception as e:
            logger.exception('cannot import module {:} ({:})'.format(name, e))
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
            logger.error('name clash for {:}'.format(name))
 
    @classmethod
    def initialise_new_object(cls):
        logger.info('initialising for new object')
        for c in cls.components.keys():
            cls.components[c].on_new_object()
        App.get_running_app().gui.reset_changes()

    @classmethod
    def initialise_previous_object(cls):
        # ensure metadata is first and stacker the last to be initialised
        logger.info('initialising for previous object')
        comps = ['Metadata'] + list(cls.components.keys() - {'Stacker', 'Metadata'}) + ['Stacker']
        for c in comps:
            cls.components[c].on_previous_object()
        App.get_running_app().gui.reset_changes()
 
    @classmethod
    def save_object(cls):
        for c in cls.components.keys():
            cls.components[c].on_save_object()

    @classmethod
    def close(cls):
        logger.debug('closedown')
        tosave = {}
        for c in cls.components.values():
            for k in c.save_settings:
                tosave[k] = getattr(c, k)
        with open(App.get_running_app().get_path('gui_settings.json'), 'w') as f:
            json.dump(tosave, f, indent=1)
        for c in cls.components.keys():
            cls.components[c].on_close()

    @classmethod
    def bind_status(cls):
        for name, inst in cls.components.items():
            cls.get('Status').bind_status(name, inst)
            #inst.info('loaded')

    def redraw(self, *args): 
        pass

    def on_new_object(self, *args): 
        pass

    def on_previous_object(self, *args):
        # treat as new object unless a component overrides this
        self.on_new_object(*args)

    def on_save_object(self, *args): 
        pass

    def on_close(self, *args): 
        pass

    def info(self, message=None, prefix=None, typ='normal'):
        self.infoline = message
