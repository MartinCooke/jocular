import os

from functools import partial
from loguru import logger
from pathlib import Path

from kivy.metrics import dp
from kivy.app import App
from kivy.uix.spinner import Spinner
from kivy.uix.button import Button
from kivymd.uix.slider import MDSlider
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.filemanager import MDFileManager

from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from jocular.widgets import LabelL, LabelR


@logger.catch()
def configurable_to_widget(text=None, name=None, spec=None, initval=None, 
	helptext=None, changed=None, textwidth=None, widgetwidth=None):
	''' creates a widget and its handler, which calls function 'changed' on any change
	'''

	if textwidth is None:
		textwidth = dp(280)
	if widgetwidth is None:
		widgetwidth = dp(150)

	font_size = '16sp'
	help_font_size = '13sp'
	color = App.get_running_app().theme_cls.accent_color

	bv = BoxLayout(padding=(dp(5), dp(5)), size_hint=(1, None), height=dp(55), 
		orientation='vertical')
	bh = BoxLayout(size_hint=(1, .55))
	bh.add_widget(Label(size_hint=(1, 1)))
	bh.add_widget(LabelR(text=text, size_hint=(None, 1), width=textwidth, font_size=font_size))

	if 'options' in spec:
		opts = spec['options']
		widget = Spinner(text=initval, values=spec['options'], 
			size_hint=(None, 1), width=widgetwidth, font_size=font_size)
		widget.bind(text=partial(__option_changed, name, spec, changed))
		bh.add_widget(widget)
		bh.add_widget(Label(size_hint=(None, 1), width=widgetwidth))

	elif 'boolean' in spec:
		opts = spec['boolean'].keys()
		# lookup names e.g. yes/no for true or false
		val = {v: k for k, v in spec['boolean'].items()}[initval]
		widget = Spinner(text=val, values=opts, size_hint=(None, 1), width=widgetwidth, 
			font_size=font_size)
		widget.bind(text=partial(__boolean_changed, name, spec, changed))
		bh.add_widget(widget)
		bh.add_widget(Label(size_hint=(None, 1), width=widgetwidth))

	elif 'switch' in spec:
		widget = MDSwitch(size_hint=(None, 1), width=widgetwidth, active=initval,
			pos_hint={'center_x': .5, 'center_y': .5})
		widget.bind(active=partial(__switch_changed, name, spec, changed))
		bh.add_widget(widget)
		bh.add_widget(Label(size_hint=(None, 1), width=widgetwidth - dp(36)))
		bh.add_widget(Label(size_hint=(None, 1), width=widgetwidth))

	elif 'float' in spec:
		fmt = spec.get('fmt', '{:.2f}')
		slabel = LabelL(text=fmt.format(initval), size_hint=(None, 1), width=.7*widgetwidth, 
			font_size=font_size, color=color)
		bh.add_widget(slabel)
		smin, smax, step = spec['float']
		widget = MDSlider(size_hint=(None, 1), width=1.3*widgetwidth, 
			step=step, min=smin, max=smax, value=float(initval))
		widget.hint_bg_color=(.6,.6,.6,1)
		widget._set_colors()
		widget.bind(value=partial(__sfloat_changed, name, spec, slabel, fmt, changed))
		bh.add_widget(widget)

	elif 'double_slider_float' in spec:
		fmt = spec.get('fmt', '{:.2f}')
		slabel = LabelL(text=fmt.format(initval), size_hint=(None, 1), 
			width=.7*widgetwidth, font_size=font_size, color=color)
		bh.add_widget(slabel)
		smin, smax = spec['double_slider_float']
		val1 = int(initval)
		val2 = abs(initval - val1)
		bh2 = BoxLayout(orientation='vertical', size_hint=(None, 1), width=1.3*widgetwidth)
		slider1 = MDSlider(size_hint=(1, .5), width=widgetwidth, 
			step=1, min=smin, max=smax, value=val1)
		slider2 = MDSlider(size_hint=(1, .5), width=widgetwidth, 
			step=.01, min=0, max=1, value=val2)
		bh2.add_widget(slider1)
		bh2.add_widget(slider2)
		slider1.bind(value=partial(
			__dfloat_changed, name, spec, slabel, fmt, changed, slider1, slider2))
		slider2.bind(value=partial(
			__dfloat_changed, name, spec, slabel, fmt, changed, slider1, slider2))
		bh.add_widget(bh2)

	elif 'action' in spec:
		widget = Button(text=spec['button'], size_hint=(None, 1), width=widgetwidth, 
			font_size=font_size)
		widget.bind(on_press=partial(__action_pressed, name, spec, changed))
		bh.add_widget(widget)
		bh.add_widget(Label(size_hint=(None, 1), width=widgetwidth))

	elif 'filechooser' in spec:
		widget = Button(text='choose...', size_hint=(None, 1), width=widgetwidth,
		 font_size=font_size)
		widget.bind(on_press=partial(__filechooser_pressed, name, spec, changed, initval))
		bh.add_widget(widget)
		bh.add_widget(Label(size_hint=(None, 1), width=widgetwidth))

	bh.add_widget(Label(size_hint=(1, 1)))

	# lower row contains only help text
	blow = BoxLayout(size_hint=(1, .45))
	blow.add_widget(Label(text=helptext, size_hint=(1, 1),
		font_size=help_font_size, color=(.5, .5, .5, 1)))
	bv.add_widget(bh)
	bv.add_widget(blow)

	return bv


def __sfloat_changed(name, spec, slabel, fmt, changed, slider, *args):
	slabel.text = fmt.format(slider.value)
	changed(name, slider.value, spec)

def __dfloat_changed(name, spec, slabel, fmt, changed, slider1, slider2, *args):
	val = slider1.value
	if val < 0:
		val -= slider2.value
	else:
		val += slider2.value
	slabel.text = fmt.format(val)
	changed(name, val, spec)

def __option_changed(name, spec, changed, widget, value, *args):
	changed(name, value, spec)

def __boolean_changed(name, spec, changed, widget, value, *args):
	changed(name, spec['boolean'][value], spec)

def __switch_changed(name, spec, changed, widget, *args):
	changed(name, widget.active, spec)

def __action_pressed(name, spec, changed, widget, *args):
	# call spec with widget also since we need to interact with it
	# to signal success/failure/state
	spec['widget'] = widget
	changed(name, spec['action'], spec)

def __filechooser_pressed(name, spec, changed, initpath, *args):
	fm = MDFileManager(search='dirs')
	fm.exit_manager = partial(exit_filemanager, fm)
	fm.select_path = partial(handle_selection, name, changed, spec, fm)
	# check if initpath is writeable and if not, bring up in home dir
	if initpath is not None:
		try:
			with open(os.path.join(initpath, '.written'), 'w') as f:
				f.write('can write')
		except Exception as e:
			initpath = None
	if initpath is None:
		initpath = str(Path.home())
	# use show disks allows showing devices 
	# fm.show_disks()
	fm.show(initpath)

def exit_filemanager(widget, *args):
	widget.close()

def handle_selection(name, changed, spec, widget, path):
	changed(name, path, spec)
	widget.close()

