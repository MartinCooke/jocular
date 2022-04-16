''' Info; toggle display of info panels
'''

from kivy.app import App
from kivy.properties import BooleanProperty
from jocular.component import Component
from jocular.settingsmanager import Settings


class Info(Component, Settings):

    show_dso = BooleanProperty(True)
    show_session = BooleanProperty(True)
    show_notes = BooleanProperty(True)
    show_status = BooleanProperty(True)
    show_image_stats = BooleanProperty(False)

    configurables = [
       ('show_dso', {
            'name': 'DSO information', 
            'switch': '',
            'help': 'Show DSO information panel (top left)'}),
       ('show_session', {
            'name': 'Session information', 
            'switch': '',
            'help': 'Show session information panel (bottom left)'}),
       ('show_notes', {
            'name': 'Observing notes', 
            'switch': '',
            'help': 'Show observing notes panel (top right)'}),
       ('show_status', {
            'name': 'Status', 
            'switch': '',
            'help': 'Show component status panel (bottom right)'}),
       ('show_image_stats', {
            'name': 'Image statistics', 
            'switch': '',
            'help': 'Show image statistics (bottom centre)'})
        ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.on_show_dso()
        self.on_show_session()
        self.on_show_notes()
        self.on_show_status()
        self.on_show_image_stats()

    def show(self, *args):
        Component.get('SettingsManager').show_settings('Info')

    def on_show_dso(self, *args):
        Component.get('DSO').show_DSO = self.show_dso

    def on_show_session(self, *args):
        Component.get('Session').show_session = self.show_session

    def on_show_notes(self, *args):
        Component.get('Notes').show_notes = self.show_notes

    def on_show_status(self, *args):
        Component.get('Status').show_status = self.show_status

    def on_show_image_stats(self, *args):
        Component.get('Monochrome').show_image_stats = self.show_image_stats
