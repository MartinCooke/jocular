''' Handles load/save of all settings. 
'''

import json
import os
from functools import partial
from loguru import logger

from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.spinner import Spinner
from kivy.metrics import dp
from kivy.properties import StringProperty, DictProperty, ListProperty
from kivy.factory import Factory
from kivy.lang import Builder

from jocular.component import Component
from jocular.formwidgets import configurable_to_widget
from jocular.panel import Panel

Builder.load_string(
    '''

<MySpinnerOption@SpinnerOption>:
    size_hint_y: None
    height: "36dp"

''')

class SettingsManager(Component, Panel):


	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		self.app = App.get_running_app()
		self.instances = {}
		self.current_panel = 'Appearance'
		self.app.gui.add_widget(self)


	def register(self, settings, name=None):
		''' keep a record of all setting instances
		'''
		self.instances[name] = settings
		logger.debug(f'registered settings for {name}')


	def on_hide(self, *args):
		for cls in self.instances.values():
			cls.apply_and_save_settings()


	def on_show(self, panel=None):
		''' Rebuild and display settings screen
		'''

		self.contents.clear_widgets()
		self.header.clear_widgets()
		self.contents.width = dp(800) # was 600

		# top spinner
		hb = BoxLayout(size_hint=(1, None), height=dp(28))
		hb.add_widget(Label(size_hint=(1, 1)))
		self.spinner = Spinner(
			text=self.current_panel,
			values=sorted(self.instances.keys()),
			option_cls=Factory.get("MySpinnerOption"),
			size_hint=(None, 1), width=dp(140), 
			font_size='16sp')
		self.spinner.bind(text=self.setting_panel_changed)
		hb.add_widget(self.spinner)
		hb.add_widget(Label(size_hint=(1, 1)))
		self.header.add_widget(hb)

		self.panel = BoxLayout(orientation='vertical', size_hint=(1, 1))
		self.contents.add_widget(self.panel)
		self.show_panel()


	def show_settings(self, panel):
		if panel not in self.instances:
			return
		self.show()
		self.spinner.text = panel


	def setting_panel_changed(self, spinner, *args):
		self.current_panel = spinner.text
		self.show_panel()


	def show_panel(self):
		''' update panel with current class settings
		'''

		cls = self.instances[self.current_panel]

		self.panel.clear_widgets()
		self.panel.add_widget(Label(size_hint=(1, 1))) # spacer

		for name, spec in cls.configurables:
			self.panel.add_widget(configurable_to_widget(
				text=spec.get('name', name),
				name=name,
				spec=spec,
				helptext=spec.get('help', ''),
				initval=getattr(cls, name), 
				changed=cls.setting_changed))

		self.panel.add_widget(Label(size_hint=(1, 1))) # spacer


	def on_touch_down(self, touch):
		handled = super().on_touch_down(touch)
		if self.collide_point(*touch.pos):
			return True
		return handled



class SettingsBase():

	configurables = ListProperty([])
	changed_settings = DictProperty({})


	def __init__(self, **kwargs):
		self.app = App.get_running_app()
		self.name = self.__class__.__name__

		settings = {}

		# load settings if they exist
		path = self.app.get_path(f'{self.name}.json')
		if os.path.exists(path):
			# report any JSON issues
			try:
				with open(path, 'r') as f:
					settings = json.load(f)
			except Exception as e:
				logger.error(f'Problem reading json file {path} ({e})')
		else:
			logger.debug(f'No {path}; setting to empty')


		# initialise values; report any issues caused e.g. by changes 
		# in types etc between versions
		for name, spec in self.configurables:
			if name in settings:
				try:
					setattr(self, name, settings[name])
				except Exception as e:
					logger.debug(f'{e}')


	@logger.catch
	def apply_and_save_settings(self):

		if not self.changed_settings:
			return

		# update values
		for p, v in self.configurables:
			if 'action' not in v and p in self.changed_settings:
				setattr(self, p, self.changed_settings[p])

		# save settings
		settings = {p: getattr(self, p) for p, v in self.configurables if 'action' not in v}
		with open(self.app.get_path(f'{self.name}.json'), 'w') as f:
			json.dump(settings, f, indent=1)

		# notify anyone who is listening
		self.settings_have_changed() 

		# clear changes for next time
		self.changed_settings = {}


	@logger.catch()	
	def setting_changed(self, name, value, spec, *args):
		''' Called by widget when a setting changes; we just store it
		'''

		# either an action or a setting change
		if 'action' in spec:
			try:
				widget = spec['widget']
				widget.text = 'processing...'
				getattr(self, spec['action'])(
					success_callback=partial(self.action_succeeded, widget),
					failure_callback=partial(self.action_failed, widget)
					)
			except Exception as e:
				logger.exception(e)

		else:
			self.changed_settings[name] = value
			if spec.get('update', True):
				setattr(self, name, value) 


	def action_succeeded(self, widget, message, *args):
		widget.text = message


	def action_failed(self, widget, message, *args):
		widget.text = message


	def settings_have_changed(self, *args):
		pass



class JSettings(SettingsBase):

	tab_name = StringProperty(None) 

	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		Component.get('SettingsManager').register(self,
			name=self.name if self.tab_name is None else self.tab_name)

