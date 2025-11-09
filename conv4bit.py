#!/usr/bin/env python3
""" Convert 4-bit terminal colorthemes between formats.

The format support is best-effort and generally expects a snippet of only the
color config, when the color config is part of a bigger config file.

By writing the OSC format to stdout, the color palette of a running terminal
can be changed, for those that support xterm-style OSC 4/10/11/12.

Copyright 2024 Jordan Torbiak
License: [MIT](https://opensource.org/license/mit/)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, cast, Callable
import argparse
import contextlib
import re
import sys


COLORS_3BIT = ['black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white']

NAME_FOR: dict[int, str] = {
    0: 'black',
    1: 'red',
    2: 'green',
    3: 'yellow',
    4: 'blue',
    5: 'magenta',
    6: 'cyan',
    7: 'white',
    8: 'black_bright',
    9: 'red_bright',
    10: 'green_bright',
    11: 'yellow_bright',
    12: 'blue_bright',
    13: 'magenta_bright',
    14: 'cyan_bright',
    15: 'white_bright',
}


@dataclass
class Color:
    r: int
    g: int
    b: int

    @staticmethod
    def parse(s: str) -> 'Color':
        if (m := re.match(r'(?:#|0x)([0-9a-fA-F]{6})', s)):
            digits = m.group(1)
            r = int(digits[0:2], 16)
            g = int(digits[2:4], 16)
            b = int(digits[4:6], 16)
            return Color(r, g, b)
        else:
            raise Exception(f'unexpected color format: {s}')

    def hex(self) -> str:
        return f'#{self.r:02x}{self.g:02x}{self.b:02x}'

@dataclass
class Theme:
    foreground: Color
    background: Color

    black: Color
    red: Color
    green: Color
    yellow: Color
    blue: Color
    magenta: Color
    cyan: Color
    white: Color

    black_bright: Color
    red_bright: Color
    green_bright: Color
    yellow_bright: Color
    blue_bright: Color
    magenta_bright: Color
    cyan_bright: Color
    white_bright: Color

    cursor: Color = field(default_factory=lambda: Color.parse('#cccccc'))
    cursor_reverse: Color = field(default_factory=lambda: Color.parse('#555555'))


def open_infile(filename: Path) -> IO:
    if filename == Path('-'):
        return cast(IO, contextlib.nullcontext(sys.stdin))
    return open(filename)

def open_outfile(filename: Path) -> IO:
    if filename == Path('-'):
        return cast(IO, contextlib.nullcontext(sys.stdout))
    return open(filename, 'w')


def read_yaml(r: IO) -> Theme:
    import yaml  # type: ignore[import-untyped]
    doc = cast(dict, yaml.safe_load(r))
    if 'color_01' in doc:
        return read_yaml_gogh(doc)
    elif 'colors' in doc and 'primary' in doc['colors']:
        return read_yaml_alacritty(doc)
    else:
        raise ValueError('unexpected yaml format')

def read_yaml_gogh(doc: dict) -> Theme:
    color_dict = {}
    for i, name in enumerate(COLORS_3BIT):
        color_dict[name] = Color.parse(doc[f'color_{i+1:02d}'])
        color_dict[f'{name}_bright'] = Color.parse(doc[f'color_{i+1+8:02d}'])
    for k in ['foreground', 'background', 'cursor']:
        color_dict[k] = Color.parse(doc[k])
    return Theme(**color_dict)

def read_yaml_alacritty(doc: dict) -> Theme:
    """ Read Alacritty YAML config. """
    color_dict = {}

    for name in ['foreground', 'background']:
        color_dict[name] = Color.parse(doc['colors']['primary'][name])

    for name in COLORS_3BIT:
        color_dict[name] = Color.parse(doc['colors']['normal'][name])
        color_dict[f'{name}_bright'] = Color.parse(doc['colors']['bright'][name])

    return Theme(**color_dict)


def read_nidx(r: IO) -> Theme:
    """ Read whitespace-separated name-value pairs.

    One pair per line. Unix toolkit style.
    """
    color_dict = {}
    for i, line in enumerate(r):
        if line.startswith('#'):
            continue
        try:
            name, hex = line.split()
        except ValueError:
            raise Exception(f'unexpected format on line {i}')
        color_dict[name] = Color.parse(hex)
    return Theme(**color_dict)

def write_nidx(w: IO, theme: Theme) -> None:
    """ Write  whitespace-separated name-value pairs. """
    keys = ['foreground', 'background']
    for key in COLORS_3BIT:
        keys.append(key)
        keys.append(f'{key}_bright')
    keys.extend(['cursor', 'cursor_reverse'])

    for k in keys:
        c = getattr(theme, k)
        print(f'{k} {c.hex()}', file=w)


def read_csv(r: IO) -> Theme:
    """ Read CSV-lite headerless (color_name,hex) """
    color_dict = {}
    for i, line in enumerate(r):
        if line.startswith('#'):
            continue
        try:
            name, hex = line.split(',')
        except ValueError:
            raise Exception(f'unexpected format on line {i}')
        color_dict[name] = Color.parse(hex)
    return Theme(**color_dict)

def write_csv(w: IO, theme: Theme) -> None:
    """ Write CSV-lite headerless (color_name,hex). """
    keys = ['foreground', 'background']
    for key in COLORS_3BIT:
        keys.append(key)
        keys.append(f'{key}_bright')
    keys.extend(['cursor', 'cursor_reverse'])

    for k in keys:
        c = getattr(theme, k)
        print(f'{k},{c.hex()}', file=w)


def read_stconf(r: IO) -> Theme:
    """ Read color config from suckless st config.h.

    Expects just the color part of the config, not the whole file.
    """
    color_for = NAME_FOR.copy()
    color_for[256] = 'background'
    color_for[257] = 'foreground'

    color_dict: dict[str, Color] = {}
    i = 0
    for line in r:
        if line.startswith('//'):
            continue
        if m := re.search(r'(?:\[(\d+)\] += +)?"(#[0-9a-fA-F]{6}")', line):
            num, hex = m.groups()
            if num is not None:
                i = int(num)
            color = Color.parse(hex)
            color_name = color_for[i]
            color_dict[color_name] = color
            i += 1

        if i > 257:
            break

    return Theme(**color_dict)

def write_stconf(w: IO, theme: Theme) -> None:
    """ Write the color config for suckless st config.h. """
    i = 0
    print('/* 8 normal colors */', file=w)
    for name in COLORS_3BIT:
        color = getattr(theme, name)
        print(f'[{i}] = "{color.hex()}",  /* {name} */', file=w)
        i += 1
    print('', file=w)

    print('/* 8 bright colors */', file=w)
    for name in [f'{x}_bright' for x in COLORS_3BIT]:
        color = getattr(theme, name)
        print(f'[{i}] = "{color.hex()}",  /* {name} */', file=w)
        i += 1
    print('', file=w)

    print('/* special colors */', file=w)
    print(f'[256] = "{theme.background.hex()}",  /* background */', file=w)
    print(f'[257] = "{theme.foreground.hex()}",  /* foreground */', file=w)


def read_xres(r: IO) -> Theme:
    """ Read colors from Xresources. """
    color_dict: dict[str, Color] = {}
    for line in r:
        if line.startswith('!') or re.search(r'^\s*$', line):
            continue
        if m := re.search(r'([^:]+): *(#[a-fA-F0-9]{6})', line):
            label, hex = m.groups()
            label = re.sub(r'.*[.*]', '', label)  # remove up to last '*' or '.'
            color = Color.parse(hex)
            if label in {'foreground', 'background'}:
                color_dict[label] = color
            elif label == 'cursorColor':
                color_dict['cursor'] = color
            elif label.startswith('color'):
                num = int(label.removeprefix('color'))
                name = NAME_FOR[num]
                color_dict[name] = color
        else:
            raise Exception(f'unexpected line format: {line}')
    return Theme(**color_dict)


def write_xres(w: IO, theme: Theme) -> None:
    """ Write colortheme in X resources format.

    Use the same format as https://terminal.sexy.
    """
    def print_color(name: str, color: Color) -> None:
        label = f'*.{name}:'
        print(f'{label:16s}{color.hex()}', file=w)

    print('! special', file=w)
    print_color('foreground', theme.foreground)
    print_color('background', theme.background)
    print_color('cursorColor', theme.cursor)

    for i, name in enumerate(COLORS_3BIT):
        print('', file=w)
        print(f'! {name}', file=w)
        print_color(f'color{i}', getattr(theme, name))
        print_color(f'color{i+8}', getattr(theme, name + '_bright'))

def write_osc(w:IO, theme: Theme) -> None:
    """ Write OSC escapes to set the color palette of a running terminal.

    Tested with: st, tmux, xterm
    VTE-based terminals supposedly support them, too.
    """
    for i, name in enumerate(COLORS_3BIT):
        c = getattr(theme, name)
        print(f'\033]4;{i};{c.hex()}\007', file=w, end='')
        c = getattr(theme, f'{name}_bright')
        print(f'\033]4;{i+8};{c.hex()}\007', file=w, end='')
    print(f'\033]10;{theme.foreground.hex()}\007', file=w, end='')
    print(f'\033]11;{theme.background.hex()}\007', file=w, end='')
    print(f'\033]12;{theme.cursor.hex()}\007', file=w, end='')


IFORMATS: dict[str, Callable[[IO], Theme]] = {
    'yaml': read_yaml,
    'yml': read_yaml,
    'nidx': read_nidx,
    'stconf': read_stconf,
    'xres': read_xres,
    'csv': read_csv,
}
OFORMATS: dict[str, Callable[[IO, Theme], None]] = {
    'stconf': write_stconf,
    'nidx': write_nidx,
    'xres': write_xres,
    'csv': write_csv,
    'osc': write_osc,
}


def main() -> None:
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='''\
convert 4-bit terminal color schemes between formats.

Formats are guessed from filenames but can also be given with --ifmt/--ofmt.
''')
    ap.add_argument('infile', default='-', type=Path, help='use "-" to read from stdin')
    ap.add_argument('outfile', default='-', type=Path, help='use "-" to write to stdout')
    ap.add_argument('--ifmt', '-i', choices=IFORMATS.keys())
    ap.add_argument('--ofmt', '-o', choices=OFORMATS.keys())

    args = ap.parse_args()

    if args.infile == Path('-') and args.ifmt is None:
        print('--ifmt must be given when reading stdin', file=sys.stderr)
        sys.exit(1)
    if args.outfile == Path('-') and args.ofmt is None:
        print('--ofmt must be given when writing to stdout', file=sys.stderr)
        sys.exit(1)

    ifmt = args.ifmt
    if ifmt is None:
        iext = args.infile.suffix.lstrip('.')
        if iext in IFORMATS:
            ifmt = iext
    if ifmt is None:
        print('unsupported input format', file=sys.stderr)
        sys.exit(1)

    ofmt = args.ofmt
    if ofmt is None:
        oext = args.outfile.suffix.lstrip('.')
        if oext in OFORMATS:
            ofmt = oext
    if ofmt is None:
        print('unsupported output format', file=sys.stderr)
        sys.exit(1)

    with (
        open_infile(args.infile) as infile,
        open_outfile(args.outfile) as outfile
    ):
        theme = IFORMATS[ifmt](infile)
        OFORMATS[ofmt](outfile, theme)

if __name__ == '__main__':
    main()
