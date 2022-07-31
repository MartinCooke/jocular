''' Support for Jocular-specific icons
'''

joc_icons = {
    'pause': '3',
    'play': 'P', # was 'n',
    'oculus': 'o',
    'last_sub': 'f',
    'first_sub': 'e',
    'next_sub': '>',
    'prev_sub': '<',
    'camera': 'b',
    'reticle': 'r', # was v
    'ROI': 'd', # was 'v'
    'fit': 'y',
    'realign': 'E',
    'clear': '0',
    'quit': 'Q',
    'settings': 'x',
    'snapshotter': 'o',
    'prev': 'F',
    'list': 'w',
    'lever': '1',
    'dot': '1',
    'redo': 'h',  # was '4'
    'new': 'i',
    'save': 'i',  # until we update
    'warn': '!',
    'error': 'W',
    'solve': 'T',
    'slew': 'H',
    'dso': 'a',
    'equip': 'H',
    'show_subs': '}', # was '*'
    'stack': '5',
    'snapshot': 'z',
    'experimental': 'c',
    'info': '}',
    'tooltips': '?'
}


def get_icon(icon_name, font_size=None, color=None):
    ''' Return a Kivy-markup icon
    '''
    font_size = f'{font_size}sp' if font_size else '17sp'
    icon = joc_icons.get(icon_name, icon_name)
    if color is None:
        return f'[font=Jocular][size={font_size}]{icon}[/size][/font]'
    color = {'r': 'ff0000', 'y': 'ffff00', 'g': '00ff00'}[color]
    return f'[font=Jocular][size={font_size}][color={color}]{icon}[/color][/size][/font]'
 