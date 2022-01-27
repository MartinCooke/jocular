''' Manages all individual components, including imports/instantiation,
    in a uniform way.
'''

import json
import importlib
from loguru import logger
from collections import OrderedDict
from kivy.app import App
from kivy.event import EventDispatcher
from kivy.properties import StringProperty, ListProperty

class Component(EventDispatcher):

    components = OrderedDict()
    infoline = StringProperty('')   # component signals state for status panel
    save_settings = ListProperty([])
    changed = StringProperty('')

    @classmethod
    def get(cls, name):
        # Returns component whose class is identified by name; loads if not found
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
        for v in cls.components.values():
            v.changed = ''
            v.on_new_object()
        App.get_running_app().gui.is_changed(False)

    @classmethod
    def initialise_previous_object(cls):
        # ensure metadata is first and stacker the last to be initialised
        logger.info('initialising for previous object')
        comps = ['Metadata'] + list(cls.components.keys() - {'Stacker', 'Metadata'}) + ['Stacker']
        for c in comps:
            cls.components[c].changed = ''
            cls.components[c].on_previous_object()
        App.get_running_app().gui.is_changed(False)
 
    @classmethod
    def changes(cls):
        ''' return a dictionary of changes since last save
        '''
        return {c: v.changed for c, v in cls.components.items() if v.changed != ''}

    @classmethod
    def save_object(cls):
        for v in cls.components.values():
            v.on_save_object()
            v.changed = ''

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

    @classmethod
    def check_for_change(cls):
        ''' Only changed if at least one component reports a change
            and the stack is non-empty
        '''
        App.get_running_app().gui.is_changed(cls.any_changes())

    @classmethod
    def any_changes(cls):
        nonempty = not cls.get('Stacker').is_empty()
        return (cls.changes() != {}) and nonempty

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

    def on_changed(self, *args):
        ''' Called when any of the component 'changed' is altered
            Check if any changes from any component and communicate to GUI
        '''
        Component.check_for_change()

    def info(self, message=None, prefix=None, typ='normal'):
        self.infoline = message
