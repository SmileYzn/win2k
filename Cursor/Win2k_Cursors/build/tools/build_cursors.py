"""Gera o tema de cursores Win2k a partir dos recursos do Windows 2000.

Uso: python3 -I build_cursors.py <dir_rsrc_user32> <dir_rsrc_ole32> <dir_tema_saida>
"""
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wincur  # noqa: E402

U32, OLE, OUT = sys.argv[1:4]
BUILD = os.path.join(OUT, 'build')
PNG = os.path.join(BUILD, 'png')
CUR = os.path.join(OUT, 'cursors')

# nome principal -> (dll, grupo, transformacao)
MAIN = {
    'default':      ('u32', '100', None),
    'text':         ('u32', '101', None),
    'vertical-text': ('u32', '101', 'rot90'),
    'wait':         ('u32', '102', None),
    'crosshair':    ('u32', '103', None),
    'up-arrow':     ('u32', '104', None),
    'nwse-resize':  ('u32', '105', None),
    'nesw-resize':  ('u32', '106', None),
    'ew-resize':    ('u32', '107', None),
    'ns-resize':    ('u32', '108', None),
    'move':         ('u32', '109', None),
    'not-allowed':  ('u32', '110', None),
    'progress':     ('u32', '111', None),
    'help':         ('u32', '112', None),
    'pencil':       ('u32', '113', None),
    'pointer':      ('u32', '114', None),
    'all-scroll':   ('u32', '32654', None),
    'no-drop':      ('ole', '1', None),
    'dnd-move':     ('ole', '2', None),
    'copy':         ('ole', '3', None),
    'alias':        ('ole', '4', None),
    'right_ptr':    ('u32', '100', 'flop'),
}

# apelidos (nomes CSS, X11 legados e hashes usados por Qt/Mozilla) -> nome principal
ALIASES = {
    'default': ['left_ptr', 'arrow', 'top_left_arrow', 'left_arrow', 'context-menu'],
    'text': ['xterm', 'ibeam'],
    'wait': ['watch'],
    'progress': ['left_ptr_watch', 'half-busy', '08e8e1c95fe2fc01f976f1e063a24ccd',
                 '3ecb610c1bf2410f44200f48c40d3599'],
    'crosshair': ['cross', 'tcross', 'cross_reverse', 'diamond_cross', 'plus', 'cell'],
    'up-arrow': ['up_arrow', 'center_ptr', 'sb_up_arrow'],
    'nwse-resize': ['size_fdiag', 'bd_double_arrow', 'nw-resize', 'se-resize',
                    'top_left_corner', 'bottom_right_corner',
                    'c7088f0f3e6c8088236ef8e1e3e70000'],
    'nesw-resize': ['size_bdiag', 'fd_double_arrow', 'ne-resize', 'sw-resize',
                    'top_right_corner', 'bottom_left_corner',
                    'fcf1c3c7cd4491d801f1e1c78f100000'],
    'ew-resize': ['size_hor', 'h_double_arrow', 'sb_h_double_arrow', 'e-resize', 'w-resize',
                  'left_side', 'right_side', 'col-resize', 'split_h',
                  '028006030e0e7ebffc7f7070c0600140', '14fef782d02440884392942c11205230'],
    'ns-resize': ['size_ver', 'v_double_arrow', 'sb_v_double_arrow', 'n-resize', 's-resize',
                  'top_side', 'bottom_side', 'row-resize', 'split_v',
                  '00008160000006810000408080010102', '2870a09082c103050810ffdffffe0204'],
    'move': ['fleur', 'size_all', '4498f0e0c1937ffe01fd06f973665830',
             '9081237383d90e509aa00f00170e968f'],
    'not-allowed': ['circle', 'crossed_circle', 'forbidden', '03b6e0fcb3499374a867c041f52298f0'],
    'no-drop': ['dnd-no-drop', 'dnd-none'],
    'help': ['question_arrow', 'whats_this', 'left_ptr_help', 'dnd-ask',
             '5c6cd98b3f3ebcb1f9c7f1c204630408', 'd9ce0ab605698f320427677b458ad60b'],
    'pencil': ['draft'],
    'pointer': ['hand', 'hand1', 'hand2', 'pointing_hand', 'grab', 'grabbing', 'openhand',
                'closedhand', '9d800788f1b08800ae810202380a0822',
                'e29285e634086352946a0e7090d73106'],
    'dnd-move': [],
    'copy': ['dnd-copy', '1081e37283d90000800003c07f3ef6bf', '6407b0e94181790501fd1e167b474872'],
    'alias': ['link', 'dnd-link', '3085a0e285430894940527032f8b26df',
              '640fb0e74195791501fd1ed57b41487f'],
}


def load_group(rsrc, grp):
    d = open(os.path.join(rsrc, 'GROUP_CURSOR', grp), 'rb').read()
    _, _, cnt = struct.unpack_from('<HHH', d, 0)
    # usa a primeira imagem do grupo (todas sao 32x32 no Win2000)
    w, h2, pl, bpp, sz, nid = struct.unpack_from('<HHHHIH', d, 6)
    c = open(os.path.join(rsrc, 'CURSOR', str(nid)), 'rb').read()
    hx, hy = struct.unpack_from('<HH', c, 0)
    w, h, _, _, px, _ = wincur._dib(c, 4, len(c) - 4, (hx, hy))
    return w, h, hx, hy, bytearray(px)


def fix_invert(w, h, px):
    """Pixels que invertem a tela viram preto com contorno branco."""
    inv = [(px[(y * w + x) * 4 + 3] == 254) for y in range(h) for x in range(w)]
    if not any(inv):
        return px
    for i, v in enumerate(inv):
        if v:
            px[i * 4 + 3] = 255
    for y in range(h):
        for x in range(w):
            o = (y * w + x) * 4
            if px[o + 3] != 0:
                continue
            near = any(0 <= x + dx < w and 0 <= y + dy < h and inv[(y + dy) * w + x + dx]
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            if near:
                px[o:o + 4] = b'\xff\xff\xff\xff'
    return px


def transform(w, h, hx, hy, px, how):
    if how == 'flop':
        out = bytearray(len(px))
        for y in range(h):
            for x in range(w):
                s = (y * w + x) * 4
                d = (y * w + (w - 1 - x)) * 4
                out[d:d + 4] = px[s:s + 4]
        return w, h, w - 1 - hx, hy, out
    if how == 'rot90':
        out = bytearray(len(px))
        for y in range(h):
            for x in range(w):
                s = (y * w + x) * 4
                nx, ny = h - 1 - y, x
                d = (ny * w + nx) * 4
                out[d:d + 4] = px[s:s + 4]
        return w, h, h - 1 - hy, hx, out
    return w, h, hx, hy, px


def write_png(path, w, h, px, scale=1):
    raw = os.path.join(HERE, 'raw')
    open(raw, 'wb').write(bytes(px))
    cmd = ['magick', '-size', '%dx%d' % (w, h), '-depth', '8', 'rgba:' + raw]
    if scale != 1:
        cmd += ['-filter', 'point', '-resize', '%d%%' % (scale * 100)]
    subprocess.run(cmd + ['PNG32:' + path], check=True)


os.makedirs(PNG, exist_ok=True)
os.makedirs(CUR, exist_ok=True)
src = {'u32': U32, 'ole': OLE}
for name, (dll, grp, how) in MAIN.items():
    w, h, hx, hy, px = load_group(src[dll], grp)
    px = fix_invert(w, h, px)
    w, h, hx, hy, px = transform(w, h, hx, hy, px, how)
    p32 = os.path.join(PNG, '%s_32.png' % name)
    p64 = os.path.join(PNG, '%s_64.png' % name)
    write_png(p32, w, h, px)
    write_png(p64, w, h, px, 2)
    cfg = os.path.join(BUILD, '%s.in' % name)
    with open(cfg, 'w') as f:
        f.write('32 %d %d png/%s_32.png\n' % (hx, hy, name))
        f.write('64 %d %d png/%s_64.png\n' % (hx * 2, hy * 2, name))
    subprocess.run(['xcursorgen', '-p', BUILD, cfg, os.path.join(CUR, name)], check=True)

for name, alist in ALIASES.items():
    for a in alist:
        link = os.path.join(CUR, a)
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(name, link)

print('cursores: %d, apelidos: %d' % (len(MAIN), sum(len(v) for v in ALIASES.values())))
