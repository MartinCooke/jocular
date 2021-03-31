''' Root widget of the application which handles drawing itself (rings) 
    and its components. Idea is to separate the main gui out entirely. Most 
    elements are defined declaratively in gui.json in the resources dir.
'''

import os
import json
import time
from functools import partial
from collections import OrderedDict

from kivy.app import App
from kivy.uix.floatlayout import FloatLayout
from kivy.clock import Clock
from kivy.logger import Logger
from kivy.core.window import Window
from kivy.properties import BooleanProperty

from jocular.widgets import (JLabel, JToggleButton, JLever, JIconButton,
    JButton, JMulti, JFilterButton)
from jocular.utils import angle360
from jocular.component import Component
from jocular.metrics import Metrics
from jocular.ring import Ring
from jocular.reticle import Reticle
from jocular.widgets import jicon


def _true(val):
    if type(val) == bool:
        return val
    if type(val) == int:
        return val == 1
    if type(val) == str:
        return val.lower() in ['1', 'true', 'yes']
    return False

class GUI(FloatLayout):

    something_has_changed = BooleanProperty(False)

    def __init__(self, config, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.disabled_controls = set({})
        self.config = config
        self.gui = OrderedDict()
        self.bind(size=self.redraw)

    def draw(self, dt=None):

        t0 = time.time()

        # construct interface for the first time; we redraw in the order originally drawn
        orig_gui = OrderedDict()
        Component.get('View')

        # handle rings first due to draw order
        origin = Metrics.get('origin')
        radii = Metrics.get('ring_radius')
        thickness = Metrics.get('ring_thickness')

        # location of capture 'saddle'
        angle = [-12.3, 12.2]
        min_a, max_a = angle360(90 - angle[0]), angle360(90 - angle[1])
        greys = {'background': .02, 'outer': .2, 'middle': .17, 'inner': .12, 'image': 0, 'capture_ring': .2}
        start_angle = {'capture_ring': angle360(min(min_a, max_a))}
        end_angle = {'capture_ring': angle360(max(min_a, max_a))}
        for nm, r in radii.items():
            if nm != 'image':
                orig_gui[nm] = {
                    'control_type': 'Ring',
                    'widget': Ring(pos=origin, radius=r, thickness=thickness[nm], grey=greys[nm],
                        start_angle=start_angle.get(nm, 0), end_angle=end_angle.get(nm, 360))
                    } 
 
        # focus/alignment reticle
        orig_gui['reticle'] = {
            'control_type': 'Reticle',
            'widget': Reticle(pos=origin, radius=radii['image'])
        }
 
        # load GUI spec and convert so widget names are keys
        with open(self.app.get_path('gui.json'), 'r') as f:
            gs = json.load(f)

        for comp, widgets in gs.items():
            for name, widget_spec in widgets.items():
                orig_gui[name] = widget_spec
                orig_gui[name]['component'] = comp

        self.gui = OrderedDict()
        # set up a variable to use for new elements such as ring annotations which need a unique name
        self.new_element_count = 0
        for name, spec in orig_gui.items():
            self.draw_element(name, spec)

        self.constructed = True

        # check if the data path is defined and if so, if it is writeable
        data_dir = self.app.data_dir
        try:
            if len(data_dir) > 0:
                with open(os.path.join(data_dir, '.writeable'), 'w') as f:
                    f.write('ok')
                os.remove(os.path.join(data_dir, '.writeable'))
            else:
                raise
        except:
            path = os.path.split(self.app.directory)[0]
            self.app.data_dir = os.path.abspath(os.path.join(path))

        Clock.schedule_once(self.load_components, 0)
        Logger.info('GUI: drawn in {:.0f}ms'.format(1000 * (time.time() - t0)))
           

    def load_components(self, dt):

        t0 = time.time()

        for c in ['Status', 'Metadata', 'Catalogues', 'DSO', 'Notes', 'Session', 'Watcher', 'Stacker', 
            'Capture', 'CaptureScript', 'Observations', 'ObservingList', 'Monochrome',
            'MultiSpectral', 'ObjectIO', 'Camera', 'FilterWheel', 'Aligner', 
            'BadPixelMap', 'Calibrator', 'Snapshotter', 'PlateSolver', 'Annotator']:
            Component.get(c)

        # bind status to components
        Component.bind_status()

        Logger.info('GUI: components loaded in {:.0f}ms'.format(1000 * (time.time() - t0)))
        t0 = time.time()

        # prepare for new object
        Component.initialise_new_object()
        Logger.info('GUI: new object initialised in {:.0f}ms'.format(1000 * (time.time() - t0)))


    def redraw(self, *args):
        ''' Redraw interface by relocating components
        '''

        # if still being constructed, do nothing
        if not hasattr(self, 'constructed'):
            return

        t0 = time.time()
        origin = Metrics.get('origin')
        ring_radius = Metrics.get('ring_radius')
        thickness = Metrics.get('ring_thickness')
 
        for name, spec in self.gui.items():
            if 'widget' in spec:
                w = spec['widget']
                if spec['control_type'] == 'Ring' and name in ring_radius:
                    w.relocate(origin=origin, radius=ring_radius[name], thickness=thickness[name])
                elif spec['control_type'] == 'Reticle':
                    w.pos = origin
                    w.radius = ring_radius['image']
                else:
                    w.relocate(origin=origin, radius=Metrics.get(spec['location']))

        Logger.debug('GUI: redrawn to {:} in {:.0f}ms'.format(Window.size, 1000 * (time.time() - t0)))

    def draw_element(self, wname, spec):
        ''' Draw element and add to gui dictionary for later redrawing
        '''

        control_type = spec['control_type']

        if control_type in {'Ring', 'Reticle'}:
            self.add_widget(spec['widget'])
            self.gui[wname] = spec 
            return

        angle = spec['angle']
        location = spec['location']
        radial = spec.get('radial', False)

        # get initial value from config, else from initial, else make it up

        if self.config.has_option('Startup', wname):
            initial_value = self.config.get('Startup', wname)
        elif 'initial' in spec:
            initial_value = spec['initial']
        elif 'values' in spec:
            initial_value = spec['values'][0]
        else:
            initial_value = 0

        rad = Metrics.get(location)
        orig = Metrics.get('origin')
        radial = spec.get('radial', False)

        # handle icons uniformly
        if 'icon' in spec and 'text' in spec:
            text = jicon(spec['icon'], font_size=spec.get('font_size', None)) + '\n' + spec['text']            
        elif 'icon' in spec:
            text = jicon(spec['icon'], font_size=spec.get('font_size', None))
        else:
            text = spec.get('text', '')

        if control_type == 'JToggleButton':
            w = JToggleButton(angle=angle, origin=orig, radius=rad, text=text, radial=radial,
                allow_no_selection=False)
            if 'group' in spec:
                w.group = spec['group']
            w.state = 'down' if _true(initial_value) else 'normal'

        elif control_type == 'JButton':
            w = JButton(angle=angle, origin=orig, radius=rad, text=text, radial=radial)

        elif control_type == 'JFilterButton':
            w = JFilterButton(angle=angle, origin=orig, radius=rad, text=text, radial=radial)

        # to do: see if we can combine with JButton
        elif control_type == 'JIconButton':
            w = JIconButton(angle=angle, origin=orig, radius=rad, icon=text)
 
        elif control_type == 'JLabel':
            w = JLabel(angle=angle, origin=orig, radius=rad, text=spec.get('text', ''))

        elif control_type == 'JMulti':
            w = JMulti(angle=angle, origin=orig, radius=rad, values=spec['values'],
                text=str(initial_value))

        elif control_type == 'JLever':

            if spec.get('groove', False):
                min_a, max_a = angle360(90 - angle[0]), angle360(90 - angle[1])
                w = Ring(pos=orig, radius=rad, thickness=Metrics.get('outer_width')/2,
                    grey=.13, start_angle=angle360(min(min_a, max_a)), 
                    end_angle=angle360(max(min_a, max_a)))
                #self.gui[_name()] = {
                self.gui['_new{:}'.format(self.new_element_count)] = {
                    'control_type': 'Ring', 
                    'widget': w,
                    'save': False,
                    'location': location}
                self.new_element_count += 1
                self.add_widget(w)

            w = JLever(angles=angle, origin=orig, radius=rad, value=initial_value, 
                values=spec['values'], 
                text=spec.get('text', jicon('lever', font_size=19)),
                radial=spec.get('radial', True),
                springy=spec.get('springy', False))

            self.add_widget(w)  # added here to get depth order right

            if spec.get('major', False):
                for vstr, v in spec['major'].items():
                    lab = JLabel(
                        radial=spec.get('radial', True), text=vstr, 
                        angle=w.value_to_angle(v), origin=orig, radius=rad)
                    self.add_widget(lab) 
                    #self.gui[_name()] = {
                    self.gui['_new{:}'.format(self.new_element_count)] = {
                        'control_type': 'JLabel', 
                        'widget': lab,
                        'save': False,
                        'location': location}
                    self.new_element_count += 1

        # post inits (may need more)
        if not 'icon' in spec:
            for f in ['font_size', 'color', 'text_width', 'background_color', 'halign', 'radial']:
                if f in spec:
                    setattr(w, f, spec[f])
  
        if control_type == 'JLever':
            w.bind(value=partial(self.on_action, wname))
        else:
            self.add_widget(w)
            w.bind(on_press=partial(self.on_action, wname))

        spec['widget'] = w
        self.gui[wname] = spec

    def initialise_component(self, component):
        ''' Push initial settings into the component when it is loaded
        '''

        for k, spec in self.gui.items():
            if spec.get('component', None) == component:
                # do NOT do actions!
                if 'action' not in spec:
                    if 'group' in spec:
                        if spec['widget'].state == 'down':
                            self.on_action(k)
                    else:
                        self.on_action(k)


    def set(self, name, value, update_property=False):
        ''' Called by any component that needs to access GUI element, usually
            for something simple like changing text. Option to pass this
            change back to component via update property/
        '''

        if name not in self.gui:
            return
        spec = self.gui[name]
        ctype = spec['control_type']
        if ctype in ['JLabel', 'JMulti', 'JButton', 'JIconButton']:
            setattr(spec['widget'], 'text', str(value))
        elif ctype == 'JLever':
            getattr(spec['widget'], 'reset_value')(value)
        elif ctype == 'JToggleButton':
            # if it is a group, set all but this to normal
            if 'group' in spec:
                gname = spec['group']
                for n, v in self.gui.items():
                    if v.get('group','') == gname:
                        v['widget'].state = 'down' if n == name else 'normal'
            else:
                setattr(spec['widget'], 'state', 'down' if value else 'normal')
        if update_property:
            self.on_action(name)

    def set_prop(self, name, prop, value):
        if name not in self.gui:
            return
        spec = self.gui[name]
        if prop == 'text' and spec['control_type'] == 'JLever':
            spec['widget'].text = value
        else:
            if hasattr(spec, prop):
                setattr(spec, prop, value)


    def get(self, name):
        ''' Access value of a given component; occasionally required
        '''

        if name not in self.gui:
            return None
        spec = self.gui[name]
        w = spec['widget']
        ctype = spec['control_type']
        if ctype in ['JLabel', 'JMulti']:
            return w.text
        if ctype == 'JLever':
            return w.value
        if ctype == 'JToggleButton':
            return 1 if w.state == 'down' else 0
        return None

    def on_action(self, name, *args):
        ''' Intercept any GUI event in order to load component, before
            passing action on to component via a property change
        '''

        spec = self.gui[name]
        comp = spec['component']
        c = Component.get(comp)  # loads if needed

        if name in self.disabled_controls:
            return

        # if action is specified, simply call that method on component
        if 'action' in spec:
            getattr(c, spec['action'])()
            return

        # otherwise it involves a value change
        control = spec['control_type']

        # handle button groups
        if control == 'JToggleButton':
            if 'group' in spec:
                setattr(c, spec['group'], spec['widget'].text)
                return

        if hasattr(c, name):
            if control == 'JToggleButton':
                setattr(c, name, spec['widget'].state == 'down')
            elif control == 'JLever':
                setattr(c, name, spec['widget'].value)
            elif control == 'JMulti':
                setattr(c, name, spec['widget'].text)

    def enable(self, names=None):
        # None indicates enable everything
        if names is None:
            names = self.disabled_controls
        # remove names from disabled list
        self.disabled_controls = self.disabled_controls - set(names)
        for n in names:
            if n in self.gui:
                spec = self.gui[n]
                spec['widget'].disabled = False

    def disable(self, names):
        # adds names to disabled list
        self.disabled_controls = self.disabled_controls.union(set(names))
        for n in names:
            if n in self.gui:
                spec = self.gui[n]
                spec['widget'].disabled = True

    def on_close(self, *args):
        ''' Save certain GUI values to config. We save everything except
            actions and elements whose save property is False
        '''

        for k, spec in self.gui.items():
            if spec.get('save', True) and 'action' not in spec:
                v = self.get(k)
                if v is not None:
                    self.config.set('Startup', k, v)

    def on_something_has_changed(self, *args):
        # first check if we have an empty stack; if so, nothing has changed
        if self.something_has_changed:
            self.disable(['load_previous', 'quit'])
            spec = self.gui['new_DSO']
            if spec['widget'].text.endswith('new'):
                spec['widget'].text = spec['widget'].text[:-3] + 'save'
        else:
            self.enable(['load_previous', 'quit'])
            spec = self.gui['new_DSO']
            if spec['widget'].text.endswith('save'):
                spec['widget'].text = spec['widget'].text[:-4] + 'new'

