''' Class representing sorteable, selectable table view associated with a json model.
'''

import math
import os
import time
import operator
from functools import partial
from datetime import datetime
import numpy as np

from kivy.app import App
from kivy.logger import Logger
from kivy.core.window import Window
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.checkbox import CheckBox
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.label import Label
from kivy.lang import Builder
from kivy.properties import NumericProperty, StringProperty, BooleanProperty
from kivy.metrics import dp
from kivy.clock import Clock

Builder.load_string('''

<TableFormat>:
    font_size: '15sp'
    margin: dp(5)
    padding: dp(5), dp(5)
    text_size: self.size
    color: .5, .5, .5, 1
    valign: 'middle'

<HeaderButton>:
    on_press: root.sort_column()
    browser: None
    halign: 'center'
    background_color: .08, .08, .08, 1
    color: app.highlight_color

# row label
<TableLabel>:
    background_normal: ''
    height: dp(24)

# name column button
<TableButton>:
    column: ''
    background_normal: ''
    background_disabled_normal: ''
    background_color: 0, 0, 0, 0

<TableInput>:
    background_normal: ''
    height: dp(24)
    background_color: app.background_color
    foreground_color: app.lowlight_color
    disabled_foreground_color: app.lowlight_color
    multiline: False
    halign: 'right'
    hint_text_color: app.hint_color
    font_size: '16sp'
    padding: dp(0), dp(2), dp(0), dp(2)

# control button
<CButton>:
    size_hint: None, 1
    width: dp(180)
    text_size: self.size
    browser: None
    halign: 'center'
    #background_normal: ''
    color: app.highlight_color
    background_color: .06, .06, .06, 0

<SearchBarTextInput@TextInput>:
    background_color: .1, .1, .1, 1
    foreground_color: .5, .5, .5, 1
    multiline: False
    font_size: '16sp'

<SearchBar>:
    canvas.after:
        Color:
            rgba: app.line_color
        Line:
            points: self.x, self.y + dp(2), self.x + self.width, self.y + dp(2)
            width: 1
    size_hint: 1, None
    height: dp(32)
    font_size: '20sp'
    orientation: 'horizontal'

<TableHeader>:
    canvas.after:
        Color:
            rgba: app.line_color
        Line:
            points: self.x, self.y + dp(2), self.x + self.width, self.y + dp(2)
            width: dp(1)
    size_hint: 1, None
    height: dp(32)
    font_size: '20sp'
    orientation: 'horizontal'

<TableRow>:
    size_hint: 1, None
    height: dp(28)
    orientation: 'horizontal'

<Table>:
    size: dp(1100), dp(600)
    contents: _contents
    myheader: _header
    footer: _footer
    spacer: _spacer
    footer_actions: _footer_actions

    BoxLayout:
        orientation: 'vertical'
        pos: root.pos
        canvas.before:
            Color:
                rgba: .08, .08, .08, 1 
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            id: _header
            size_hint: 1, None
            height: dp(64)
            orientation: 'vertical'

        BoxLayout:
            id: _allcontents
            orientation: 'horizontal'
            size_hint: 1, 1                

            BoxLayout:
                id: _contents
                size_hint: None, 1
                width: root.width - dp(30)
                orientation: 'vertical'

            Slider:
                size_hint: None, 1
                cursor_size: [dp(25), dp(25)]
                width: dp(30)
                disabled: root.n_matching < root.n_rows
                min: 0
                max: max(0, root.n_matching - root.n_rows)
                step: 1
                value: round(max(0, root.n_matching - root.n_rows) - root.current_row)
                on_value: root.current_row = round(max(0, root.n_matching - root.n_rows) - self.value)
                orientation: 'vertical'
                padding: dp(16)

        BoxLayout:
            id: _spacer
            size_hint: 1, None
            canvas.after:
                Color:
                    rgba: app.line_color
                Line:
                    points: self.x, self.y + self.height, self.x + self.width, self.y + self.height
                    width: 1
            size_hint: 1, None
            height: dp(4)
            orientation: 'horizontal'

        BoxLayout:
            id: _footer
            size_hint: 1, None
            height: dp(32)
            orientation: 'horizontal'

            CButton:
                width: dp(80)
                text: 'select all'
                on_press: root.select_all()

            CButton:
                text: 'deselect all'
                width: dp(95)
                on_press: root.deselect_all()

            TableLabel:
                size_hint: None, 1
                width: dp(120)
                text: '{:d} of {:d}'.format(root.n_matching, root.n_rows_total)

            BoxLayout:
                id: _footer_actions
                height: dp(32)
                orientation: 'horizontal'
                
            CButton:
                width: dp(70)
                text: 'export'
                on_press: root.export(self)

            CButton:
                width: dp(50)
                text: 'close'
                halign: 'right'
                on_press: root.hide()

''')

class TableFormat:
    pass

# header column button (controls sorting)
class HeaderButton(Button, TableFormat):

    def __init__(self, table=None, column_name=None, column_type=None, sort_type=None, **kwargs):
        super().__init__(**kwargs)
        self.column_name = column_name
        self.table = table
        self.column_type = column_type
        self.sort_type = sort_type

    def sort_column(self):
        self.table.current_sort = {
            'name': self.column_name,
            'type': self.column_type,
            'sort_type': self.sort_type
        }
        self.table.sort_column()

# ordinary label
class TableLabel(Label, TableFormat):
    pass

# control button at lower of screen
class CButton(Button, TableFormat):
    pass

# ordinary button
class TableButton(Button, TableFormat):
    pass

# ordinary button
class TableInput(TextInput, TableFormat):
    pass

# table header line i.e. click-to-sort column headers -----------------------

class TableHeader(BoxLayout):

    def __init__(self, table, **kwargs):
        super().__init__(**kwargs)
        self.table = table

        # selection column
        self.add_widget(HeaderButton(size_hint_x=None, width=dp(20), halign='center', 
            table=table, text=' ', column_name='Selected', column_type=str))

        for i, (colname, colprops) in enumerate(table.cols.items()):

            width = colprops.get('w', 100)
            self.add_widget(HeaderButton(
                text=colname,
                size_hint_x=width if width < 2 else None,
                width=dp(width) if width >= 2 else width,
                halign=colprops.get('align', 'center'),
                column_name=colprops.get('field', colname),
                column_type=colprops.get('type', str),
                sort_type=colprops.get('sort', 'normal'),
                table=table
                ))

    def resize(self, *args):
        pass

# a single row of the table ----------------------

class TableRow(BoxLayout):

    def __init__(self, table, **kwargs):

        self.table = table
        super().__init__(**kwargs)

        self.updating = True  # flag to prevent updating textinput fields during redrawing

        # construct selector column
        w = CheckBox(size_hint_x=None, width=dp(20))
        w.bind(active=self.select_row)
        self.add_widget(w)

        self.fields = {'Selected': w}

        for colname, colprops in self.table.cols.items():

            width = colprops.get('w', 100)

            # input field; any text gets saved to self.data[key][colname]
            if 'input' in colprops:
                w = TableInput(size_hint_x=width if width < 2 else None,
                    width=dp(width) if width >= 2 else width)
                w.bind(text=partial(self.input_changed, colprops.get('field', colname)))

            else:              
                if 'action' in colprops:
                    wtype = TableButton
                else:
                    wtype = TableLabel

               # width = colprops.get('w', 100)
                w = wtype(
                    text='',
                    size_hint_x=width if width < 2 else None,
                    width=dp(width) if width >= 2 else width,
                    halign=colprops.get('align', 'center'),
                    shorten=True,
                    shorten_from='right')

                if 'action' in colprops:
                    w.bind(on_press=self.row_clicked)  # add partial with column name

            self.add_widget(w)
            self.key = None

            self.fields[colprops.get('field', colname)] = w 

        self.updating = False


    def row_clicked(self, *args):
        # only supports one at present <-- need to fix this using partial
        for colname, colprops in self.table.cols.items():
            if 'action' in colprops:
                colprops['action'](self)
                return

    # prevent click thru to beneath
    def on_touch_down(self, touch):
        if self.table.hidden:
            return
        handled = super().on_touch_down(touch)
        if self.collide_point(*touch.pos):
            return True
        return handled

    def select_row(self, *args):
        if self.fields['Selected'].active:
            self.table.selected.add(self.key)
        elif self.key in self.table.selected:
            self.table.selected.remove(self.key)

    def input_changed(self, colname, widgy, value):
        if not self.updating:
            if self.key is not None:
                if self.key in self.table.data:
                    self.table.data[self.key][colname] = value
 
    def update_row(self, row, key=None, empty=False):

        self.updating = True # don't allow input_changed to fire while redrawing
        if not empty:
            self.key = key
            self.fields['Selected'].active = self.key in self.table.selected
            self.fields['Selected'].disabled = False
        else:
            self.fields['Selected'].active = False
            self.fields['Selected'].disabled = True

        for colname, colprops in self.table.cols.items():
            field = colprops.get('field', colname)
            display_fn = colprops.get('display_fn', str)
            self.fields[field].text = ''
            if not empty and (field in row):
                val = row[field]
                vtype = type(val)
                if vtype == str:
                    self.fields[field].text = display_fn(val)
                elif not np.isnan(val):
                    self.fields[field].text = display_fn(val)
        self.updating = False

#-------------------------------------------------------------------------------------------
# table search line i.e. column filters

class SearchBar(BoxLayout):

    def __init__(self, table, **kwargs):

        self.table = table
        super().__init__(**kwargs)

        self.sorted_column = 'Name'
        self.reverse_sort = {'Name': False}

        self.filters = []

        w = SearchFilter(text='', size_hint_x=None, width=dp(20), 
            table=table, column='Selected', column_type=str)
        self.add_widget(w)
        # self.filters.append(w)

        for colname, colprops in self.table.cols.items():
            width = colprops.get('w', 100)
            w = SearchFilter(
                text='',
                size_hint_x=dp(width) if width < 2 else None,
                width=dp(width) if width >= 2 else 1,
                column=colprops.get('field', colname),
                table=table,
                val_fn=colprops.get('val_fn', None),
                column_type=colprops.get('type', str)
                )
            self.add_widget(w)
            self.filters.append(w)

        self.add_widget(CButton(text='clear', width=dp(50), on_press=self.clear_search))

    def clear_search(self, *args):
        for f in self.filters:
            f.text = ''
        self.table.search_results = list(self.table.data.keys())
        self.table.on_search_results()

    def resize(self, *args):
        pass

    def combine_results(self):
        t0 = time.time()
        # these two lines ~ 10ms
        l = [s.filtered for s in self.filters]
        self.table.search_results = list(set.intersection(*l)) # causes update
        # this takes ~ 50ms
        self.table.on_search_results()

    def reapply_filters(self):
        # called whenever the underlying table data has changed
        for f in self.filters:
            f.has_had_text = False
            f.on_text(f, f.text)
        self.combine_results()

#-------------------------------------------------------------------------------------------
# an individual column filter

# support methods to extract args/operators for filtering operations
def parg(s):
    # parse single arg
    s = s.strip()
    try:
        if s[0] not in '=!<>':
            s = '=' + s
        rest = s[1:].strip()
        if rest:
            return {s[0]: rest}
        else:
            return {}
    except:
        return {}
    
def parse_args(s):
    # parse normal or comma-sep arg
    try:
        s = s.strip()
        if ',' not in s:
            return parg(s)
        p1, _, p2 = s.strip().partition(',')
        p1 = p1.strip()
        p2 = p2.strip()
        d = {}
        if p1 and (p1[0] not in '<>'):
            d['>'] = p1
        elif p1:
            d[p1[0]] = p1[1:].strip()
        if p2 and (p2[0] not in '<>'):
            d['<'] = p2
        elif p2:
            d[p2[0]] = p2[1:].strip()
        return d
    except:
        return {}

class SearchBarTextInput(TextInput):
    pass

class SearchFilter(SearchBarTextInput):

    def __init__(self, table=None, column=None, column_type=None, val_fn=None, **kwargs):

        self.table = table
        self.column = column
        self.column_type = column_type
        self.val_fn = val_fn
        self.has_had_text = False   # see comment in on_text for the why
        super().__init__(**kwargs)

        # current set that matches filter for this column
        self.filtered = set({})


    def on_text(self, instance, value):
        ''' Applies search filter when user types. We use a flag to indicate if 
        the search field has ever contained text. If so, when it becomes empty 
        is is necessary to update the results. Otherwise, we don't update on empty 
        to avoid multiple identical updates.
        '''

        ''' Timing-wise, the search is pretty fast actually about 30ms for 40k rows; takes longer to then
            intersect the results and redraw; could be worth optimising for large catalogues, but not yet
        '''


        value = value.strip()

        if not value:
            self.filtered = set(self.table.data.keys())
            if self.has_had_text:
                self.table.searchbar.combine_results()
            return

        try:

            objs = self.table.data
            col = self.column
            col_type = self.column_type

            if len(value) > 0:

                self.has_had_text = True

                # select column where it exists
                objs = {k: v[col] for k, v in objs.items() if col in v}

                if self.column_type == str:

                    objs = {k: v.lower() for k, v in objs.items()}
                    value = value.lower()

                    # to do: had ! or != for not equal

                    # use wildcard syntax, and = for exact match
                    if value[0] == '*':
                        if len(value) > 1:
                            if value[-1] == '*':
                                objs = {k: v for k, v in objs.items() if value[1:-1] in v}
                            else:
                                objs = {k: v for k, v in objs.items() if v.endswith(value[1:])}
                    elif value[0] == '=':
                        objs = {k: v for k, v in objs.items() if v == value[1:]}
                    elif value[0] == '!':
                        objs = {k: v for k, v in objs.items() if v != value[1:]}
                    else:
                        if value[-1] == '*':
                            value = value[:-1]
                        objs = {k: v for k, v in objs.items() if v.startswith(value)}


                elif self.column_type in [float, int]:

                    objs = {k: col_type(v) for k, v in objs.items()}
                    col = self.column

                    ''' allow expressions of the form =x, !x or
                        intervals using either x,y or >x, <y
                        (or just >x for example). If the interval
                        is 'normal' e.g. 3 < x < 8 then choose x
                        in range [3, 8]; if interval is exclusive
                        e.g. <3, >10, treat as an 'or' and return
                        objects that satisfy either constraint. This
                        is useful for situations like hours spanning
                        midnight
                    '''

                    # can use x,y >x, <y =x, !x (not equal)
                    ops = parse_args(value)
                    for k, v in ops.items():
                        #ops[k] = self.column_type(v)
                        ops[k] = float(v)

                    # check if it is and or an (implicit) or
                    if ('<' in ops) and ('>' in ops) and (ops['<'] < ops['>']):
                        # it is an or
                        comp_value = ops['<']
                        if self.val_fn:
                            comp_value = self.val_fn(comp_value)
                        objs1 = {k: v for k, v in objs.items() if v <= comp_value}
                        comp_value = ops['>']
                        if self.val_fn:
                            comp_value = self.val_fn(comp_value)
                        objs2 = {k: v for k, v in objs.items() if v >= comp_value}
                        objs = {**objs1, **objs2}

                    else:
                        # ops is a dict with keys in 
                        #   =, !, >, <
                        for op, comp_value in ops.items():
                            if self.val_fn:
                                comp_value = self.val_fn(comp_value)
                            if op == '=':
                                objs = {k: v for k, v in objs.items() if v == comp_value}
                            elif op == '!':
                                objs = {k: v for k, v in objs.items() if v != comp_value}
                            elif op == '>':
                                objs = {k: v for k, v in objs.items() if v >= comp_value}
                            elif op == '<':
                                objs = {k: v for k, v in objs.items() if v <= comp_value}

            self.filtered = set(objs.keys())

            # update search results by intersecting with current search results from other columns
            # also does the redraw so quite expensive
            self.table.searchbar.combine_results()

        except Exception:
            pass

#-------------------------------------------------------------------------------------------
# Main Table class

class Table(FloatLayout):

    n_rows = NumericProperty(0)      # num visible rows
    n_matching = NumericProperty(0)  # number matching search/filter criteria
    current_row = NumericProperty(0)
    n_rows_total = NumericProperty(0)
    name = StringProperty('')
    description = StringProperty('')
    hidden = BooleanProperty(True)

    def __init__(self, size=None, data=None, cols=None, name='', 
        actions=None, controls=None,
        description='',
        update_on_show=True, on_show_method=None, on_hide_method=None, 
        initial_sort_column=None, initial_sort_direction=None, **kwargs):


        t0 = time.time()
        self.initialising = True  # to prevent redraw
        super().__init__(**kwargs)

        self.data = data
        self.n_rows_total = len(self.data)   # need to ensure this is kept updated
        self.cols = cols
        self.name = name
        self.description = description

        # user can either provide a set of button labels and method calls
        # via actions
        self.actions = actions

        # or (new in v0.3) a widget that is handled externally to table
        self.controls = controls

        self.update_on_show = update_on_show
        self.selected = set({})
        self.on_show_method = on_show_method
        self.on_hide_method = on_hide_method

        self.initial_sort_direction = initial_sort_direction
        if initial_sort_column is not None:
            if initial_sort_column in cols:
                vals = cols[initial_sort_column]
                self.current_sort = {
                    'name': initial_sort_column,
                    'type': vals.get('type', str),
                    'sort_type': vals.get('sort','')
                }

        self.filters = {}
        self.reverse_sort = {}
        self.search_results = list(self.data.keys())

        self.initialising = False  # now allow redraw
        self.size = Window.size
        self.redraw()
        # the redraw takes the time
        Logger.debug('Table: {:} built in {:.0f} ms'.format(name, 1000*(time.time() - t0)))


    def redraw(self, *args):

        if self.initialising:
            return

        t0 = time.time()

        self.redrawing = True

        if not hasattr(self, 'header'):
            # generate header/searchbar components
            self.header = TableHeader(self)
            self.myheader.add_widget(self.header)
            self.searchbar = SearchBar(self)
            self.myheader.add_widget(self.searchbar)
            self.empty_row = TableRow(self)
        else: # remove rows
            for r in self.rows:
                self.contents.remove_widget(r)

        # new in v0.5
        h = self.height - self.myheader.height - self.footer.height
        nrows = int(h / self.empty_row.height)
        spare = h - nrows * self.empty_row.height
        self.rows = []
        for i in range(0, nrows):
            r = TableRow(self)
            self.rows.append(r)
        self.n_rows = len(self.rows)

        for r in self.rows:
            self.contents.add_widget(r)
        self.spacer.height = spare

        # about 300 ms for DSO table
        self.footer_actions.clear_widgets()
        if self.actions:
            for k, v in self.actions.items():
                self.footer_actions.add_widget(CButton(text=k, on_press=v))

        elif self.controls:
            self.footer_actions.add_widget(self.controls)
 
        self.redrawing = False

        # about 100 ms for DSO table
        self.on_search_results()

        if self.initial_sort_direction is not None:
            self.sort_column(reverse=self.initial_sort_direction)


    def on_search_results(self, *args):

        if self.initialising: #  or self.redrawing:
            return

        self.current_row = 0
        self.n_matching = len(self.search_results)
        self.sort_column(reverse=False)
        self.update_display()

    def update(self, *args):
        # performs immediate update of table contents following a change
        # typically called on show and also from clients who make changes to data

        self.selected = {s for s in self.selected if s in self.data}
        self.n_rows_total = len(self.data)
        if hasattr(self, 'searchbar'):
            self.searchbar.reapply_filters()

    def update_display(self, *args): 
        # populate screen cells with current data

        last_row = min(self.n_matching, self.current_row + self.n_rows)
        results = self.search_results[self.current_row: last_row]

        for i, r in enumerate(results):
            # catch odd bug and log it
            if r in self.data:
                self.rows[i].update_row(self.data[r], key=r)
            else:
                Logger.debug('Table: cannot find {:} in table'.format(r))

        for j in range(last_row - self.current_row, self.n_rows):  # clear rest
            self.rows[j].update_row(self.empty_row, empty=True)

    def show(self, *args):

        # only allow resize when it is showing so as not to slow down general resizing...
        self.bind(size=self.redraw)

        # redraw if size has changed since last hide
        self.pos = 0, 0
        if hasattr(self, 'size_on_hide') and self.size_on_hide != self.size:
            self.redraw()

        if self.on_show_method:
            self.on_show_method()

        if self.update_on_show:
            self.update()
        else:
            self.update_display()

        self.hidden = False

    def hide(self, *args):

        self.unbind(size=self.redraw)
        if self.on_hide_method:
            self.on_hide_method()
        self.x = -10 * self.width
        self.size_on_hide = self.size.copy() # don't use size as it is a reference
        self.hidden = True

    def on_current_row(self, *args):
        self.update_display()

    def select_all(self, *args):
        self.selected = set(self.search_results)
        self.update_display()

    def deselect_all(self, *args):
        self.selected = set({})
        self.update_display()

    def select(self, to_select):
        self.selected = set(to_select)
        self.update_display()

    def export(self, but):
        def no_nl(s):
            return s.replace('\n', ' ')

        self.export_button = but
        self.orig_export_button_color = but.color
        but.color = [1, 0, 0, 1]
        cols = self.cols.keys()
        when = datetime.now().strftime('%d_%b_%y_%H_%M')

        path = os.path.join(App.get_running_app().get_path('exports'), 
            '{:}_{:}.csv'.format(self.name.replace(' ','_'), when))
        with open(path, 'w') as f:
            f.write(','.join(cols) + '\n')
            cols = [v.get('field', k) for k, v in self.cols.items()]
            for s in self.search_results:
                sd = self.data[s]
                f.write(','.join([no_nl(str(sd.get(c,''))) for c in cols]))
                f.write('\n')
        Clock.schedule_once(self.change_export_button, 1)

    def change_export_button(self, dt):
        self.export_button.color = self.orig_export_button_color

    def get_selected(self):
        return self.selected

    def on_touch_down(self, touch):
        if self.hidden:
            return
        handled = super().on_touch_down(touch)
        if self.collide_point(*touch.pos):
            return True
        return handled

    def sort_column(self, reverse=True):

        def defaultsplit(x, default):
            a = x.split()
            if len(a) == 0:
                return '', default
            elif len(a) == 1:
                return a[0], default
            elif a[1].isdigit():
                return a[0], float(a[1])
            elif a[0].isdigit():
                return float(a[0]), a[1]
            else:
                return x, default

        def null_value(v):
            return (isinstance(v, str) and v.strip() == '') or (isinstance(v, float) and math.isnan(v))

        if self.initialising or self.redrawing:
            return

        if not hasattr(self, 'current_sort'):
            return

        column_name = self.current_sort['name']
        column_type = self.current_sort['type']
        sort_type = self.current_sort['sort_type']

        # toggle sort direction
        if column_name in self.reverse_sort:
            if reverse:
                self.reverse_sort[column_name] = not self.reverse_sort[column_name]
        else:
            self.reverse_sort[column_name] = False

        # current filtered results
        current = np.array(self.search_results)

        # set up dict from position to value for current column, where column exists
        x = {i: self.data[k][column_name] for i, k in enumerate(current) if column_name in self.data[k]}

        # remove any null values that have crept in
        # x = {i: v for i, v in x.items() if v}
        x = {i: v for i, v in x.items() if not null_value(v)}

        if not x:
            return

        # store indices that won't be sorted as they don't have a value
        blank_indices = list(set(np.arange(len(self.search_results))) - set(x.keys()))

        # catch specialised sorts first
        if type(sort_type) == dict:
            if 'catalog' in sort_type: 
                # catalog sort sorts first and second columns e.g. NGC 1
                vals = [defaultsplit(str(v), 0) for v in x.values()]
                cat_sort_index = np.lexsort(([v[1] for v in vals], [v[0] for v in vals]))
                sort_index = np.array(list(x.keys()))[cat_sort_index]

            elif 'DateFormat' in sort_type:
                fmt = sort_type['DateFormat']
                x = {k: datetime.strptime(v, fmt) for k, v in x.items()}
                sort_index = [i for i, j in sorted(x.items(), key=operator.itemgetter(1))]

        elif column_type in [str, float, int]:
            x = {k: column_type(v) for k, v in x.items()}
            sort_index = [i for i, j in sorted(x.items(), key=operator.itemgetter(1))]
 
        else:
            sort_index = np.argsort(x.values())

        # reverse if necessary
        if self.reverse_sort[column_name]:
            sort_index = sort_index[::-1]

        # append blank indices
        self.search_results = list(current[sort_index]) + list(current[blank_indices])

        self.update_display()
