"""The look TowerWitch shares with ELMER.

The day palette is elmer.css's :root, token for token, so the two read as
one program on two screens: the same charcoal-navy surfaces, one amber
accent, mono uppercase labels, colour only where it means something. Night
keeps the same names and shifts every value to red, so nothing else in the
program needs to know which it is wearing.

Tk cannot round a corner or letter-space a word, so this is the part of that
look Tk can carry: surfaces, lines, type, and where the accent goes.
"""
from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk

SANS = 'DejaVu Sans'
MONO = 'DejaVu Sans Mono'


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str          # the page
    panel: str       # a card on it
    panel2: str      # a control on the card
    hover: str       # that control under the finger
    line: str        # hairlines
    line2: str       # control borders
    text: str
    dim: str
    dimmer: str
    accent: str      # the one colour that asks for attention
    accent_hi: str   # the accent under the finger
    accent_ink: str  # text on an accent-filled control
    select: str      # the chosen row
    green: str       # good
    amber: str       # wait, or look
    red: str         # bad
    blue: str
    cyan: str
    violet: str


DAY = Palette(
    name='day',
    bg='#0d1117', panel='#151b23', panel2='#1b2430', hover='#2c3a49',
    line='#2a3441', line2='#384658',
    text='#e6edf3', dim='#8b98a5', dimmer='#626e7b',
    accent='#ffb454', accent_hi='#ffc16f', accent_ink='#241802',
    select='#2b2416',
    green='#3fb950', amber='#ffb454', red='#f85149',
    blue='#58a6ff', cyan='#39d3d8', violet='#bc8cff',
)

# Everything red, so a dark-adapted eye stays that way. With one hue to work
# in, state is carried by brightness instead: good is the brightest, bad the
# dimmest, which is the order they matter in at night.
NIGHT = Palette(
    name='night',
    bg='#0a0000', panel='#140000', panel2='#1e0000', hover='#2e0000',
    line='#3a0000', line2='#4c0000',
    text='#e04848', dim='#a83636', dimmer='#742626',
    accent='#ff6b6b', accent_hi='#ff8585', accent_ink='#1a0000',
    select='#2a0a0a',
    green='#ff6b6b', amber='#c94848', red='#8a2b2b',
    blue='#c94848', cyan='#c94848', violet='#c94848',
)


def font(size, weight='normal', mono=False):
    return (MONO if mono else SANS, size, weight)


def apply(style, root, p):
    """Every ttk style TowerWitch uses, from one palette."""
    style.theme_use('clam')
    root.configure(bg=p.bg)

    # Surfaces. The top bar sits on a panel with a hairline under it, the
    # way ELMER's does; the rest of the page is the page.
    style.configure('TFrame', background=p.bg)
    style.configure('Topbar.TFrame', background=p.panel)
    style.configure('TSeparator', background=p.line)

    # Type. Body sans; labels that name a thing in mono, small, dim - the
    # panel-title and table-header voice.
    style.configure('TLabel', background=p.bg, foreground=p.text, font=font(11))
    style.configure('Topbar.TLabel', background=p.panel, foreground=p.text, font=font(11))
    style.configure('Brand.TLabel', background=p.panel, foreground=p.accent,
                    font=font(17, 'bold', mono=True))
    style.configure('BrandSub.TLabel', background=p.panel, foreground=p.dimmer, font=font(8))
    style.configure('Chip.TLabel', background=p.panel2, foreground=p.text,
                    font=font(11), padding=(9, 4))
    style.configure('Dim.TLabel', background=p.bg, foreground=p.dim, font=font(10))
    style.configure('Title.TLabel', background=p.bg, foreground=p.dimmer,
                    font=font(9, 'bold', mono=True))

    # Buttons: a control on the card, a step lighter under the finger. The
    # primary one is filled with the accent - one per screen.
    style.configure('TButton', background=p.panel2, foreground=p.text,
                    bordercolor=p.line2, lightcolor=p.panel2, darkcolor=p.panel2,
                    focuscolor=p.panel2, padding=(12, 8), font=font(11))
    style.map('TButton',
              background=[('disabled', p.panel), ('pressed', p.hover), ('active', p.hover)],
              foreground=[('disabled', p.dimmer), ('pressed', p.text), ('active', p.text)],
              bordercolor=[('active', p.accent), ('!active', p.line2)])
    style.configure('Primary.TButton', background=p.accent, foreground=p.accent_ink,
                    bordercolor=p.accent, lightcolor=p.accent, darkcolor=p.accent,
                    focuscolor=p.accent, font=font(11, 'bold'))
    style.map('Primary.TButton',
              background=[('disabled', p.panel2), ('pressed', p.accent_hi), ('active', p.accent_hi)],
              foreground=[('disabled', p.dimmer), ('pressed', p.accent_ink), ('active', p.accent_ink)],
              bordercolor=[('disabled', p.line2), ('!disabled', p.accent)])
    style.configure('Danger.TButton', foreground=p.red, bordercolor=p.red)
    style.map('Danger.TButton', foreground=[('active', p.red)], bordercolor=[('active', p.red)])
    # The Refresh button while the lists are stale: it flashes between its
    # ordinary self and the accent, which is the colour that asks.
    style.configure('Stale.TButton', background=p.accent, foreground=p.accent_ink,
                    bordercolor=p.accent, lightcolor=p.accent, darkcolor=p.accent)

    style.configure('TCheckbutton', background=p.bg, foreground=p.text, font=font(11),
                    indicatorbackground=p.panel2, indicatorforeground=p.accent,
                    focuscolor=p.bg)
    style.map('TCheckbutton',
              background=[('active', p.bg)],
              indicatorbackground=[('selected', p.panel2), ('active', p.hover)])

    # Tabs, as ELMER's nav: dim text in a row, the current one in the accent
    # on a panel with a border, the rest on nothing.
    style.configure('TNotebook', background=p.bg, borderwidth=0, tabmargins=(0, 4, 0, 0),
                    bordercolor=p.bg, lightcolor=p.bg, darkcolor=p.bg)
    style.configure('TNotebook.Tab', padding=(14, 9), font=font(11), borderwidth=1,
                    focuscolor=p.panel)
    style.map('TNotebook.Tab',
              background=[('selected', p.panel), ('active', p.panel2), ('!selected', p.bg)],
              foreground=[('selected', p.accent), ('active', p.text), ('!selected', p.dim)],
              bordercolor=[('selected', p.line2), ('!selected', p.bg)],
              lightcolor=[('selected', p.panel), ('!selected', p.bg)],
              darkcolor=[('selected', p.panel), ('!selected', p.bg)])

    # Tables: rows on a panel, hairlines only, headers in the label voice.
    style.configure('Treeview', background=p.panel, foreground=p.text,
                    fieldbackground=p.panel, font=font(11), rowheight=30,
                    borderwidth=0, relief='flat',
                    bordercolor=p.bg, lightcolor=p.bg, darkcolor=p.bg)
    style.map('Treeview',
              background=[('selected', p.select)],
              foreground=[('selected', p.accent)])
    style.configure('Treeview.Heading', background=p.panel, foreground=p.dimmer,
                    font=font(9, 'bold', mono=True), padding=(6, 6),
                    borderwidth=0, relief='flat',
                    bordercolor=p.line, lightcolor=p.panel, darkcolor=p.panel)
    style.map('Treeview.Heading',
              background=[('active', p.panel2), ('!active', p.panel)],
              foreground=[('active', p.dim), ('!active', p.dimmer)])

    # A titled panel - the GPS dashboard - is a card with a hairline edge.
    style.configure('TLabelframe', background=p.bg, borderwidth=1, relief='solid',
                    bordercolor=p.line, lightcolor=p.line, darkcolor=p.line)
    style.configure('TLabelframe.Label', background=p.bg, foreground=p.dimmer,
                    font=font(9, 'bold', mono=True))

    style.configure('Vertical.TScrollbar', background=p.line2, troughcolor=p.bg,
                    bordercolor=p.bg, arrowcolor=p.dim, relief='flat')
    style.map('Vertical.TScrollbar',
              background=[('pressed', p.hover), ('active', p.hover)])


def dress(widget):
    """Table headers and panel titles in ELMER's label voice: uppercase.
    Walks the tree once the tabs exist."""
    if isinstance(widget, ttk.Treeview):
        for col in widget['columns']:
            text = widget.heading(col, 'text')
            if text:
                widget.heading(col, text=text.upper(), anchor='w')
    elif isinstance(widget, ttk.LabelFrame):
        text = widget.cget('text')
        if text:
            widget.configure(text=text.upper())
    for child in widget.winfo_children():
        dress(child)
