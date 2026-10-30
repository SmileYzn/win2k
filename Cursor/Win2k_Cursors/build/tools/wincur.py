"""Decodificador minimo de .cur/.ico/.ani do Windows (sem PIL).

decode_cur(bytes) -> lista de (w, h, hotx, hoty, rgba_bytes, n_invert)
decode_ani(bytes) -> (frames, rates, seq, default_rate_jiffies)
Pixels de "inverter tela" (AND=1, XOR!=0) viram preto opaco com borda
nao tratada aqui; n_invert informa quantos existiam.
"""
import struct


def _dib(data, off, size, hot):
    hx, hy = hot
    if data[off:off + 8] == b'\x89PNG\r\n\x1a\n':
        raise ValueError('PNG embutido nao suportado')
    (hsz, w, h2, planes, bpp, comp, isz, _, _, clr, _) = struct.unpack_from('<IiiHHIIiiII', data, off)
    h = h2 // 2
    p = off + hsz
    pal = []
    if bpp <= 8:
        n = clr or (1 << bpp)
        for i in range(n):
            b, g, r, _ = data[p + 4 * i:p + 4 * i + 4]
            pal.append((r, g, b))
        p += 4 * n
    xstride = ((w * bpp + 31) // 32) * 4
    astride = ((w + 31) // 32) * 4
    xor = p
    andm = xor + xstride * h
    out = bytearray(w * h * 4)
    ninv = 0
    for y in range(h):
        row = h - 1 - y  # DIB de baixo para cima
        for x in range(w):
            a = (data[andm + row * astride + x // 8] >> (7 - x % 8)) & 1 if bpp != 32 else 0
            if bpp == 1:
                idx = (data[xor + row * xstride + x // 8] >> (7 - x % 8)) & 1
                c = pal[idx]
            elif bpp == 4:
                byte = data[xor + row * xstride + x // 2]
                idx = (byte >> 4) if x % 2 == 0 else (byte & 15)
                c = pal[idx]
            elif bpp == 8:
                c = pal[data[xor + row * xstride + x]]
            elif bpp == 24:
                q = xor + row * xstride + x * 3
                c = (data[q + 2], data[q + 1], data[q])
            elif bpp == 32:
                q = xor + row * xstride + x * 4
                c = (data[q + 2], data[q + 1], data[q])
                alpha = data[q + 3]
            else:
                raise ValueError('bpp %d' % bpp)
            o = (y * w + x) * 4
            if bpp == 32:
                out[o:o + 4] = bytes((c[0], c[1], c[2], alpha))
            elif a == 0:
                out[o:o + 4] = bytes((c[0], c[1], c[2], 255))
            elif c == (0, 0, 0):
                out[o:o + 4] = b'\0\0\0\0'
            else:
                ninv += 1  # pixel que inverte a tela: marcado com alpha 254
                out[o:o + 4] = bytes((0, 0, 0, 254))
    return (w, h, hx, hy, bytes(out), ninv)


def decode_cur(data):
    _, typ, cnt = struct.unpack_from('<HHH', data, 0)
    res = []
    for i in range(cnt):
        w, h, cc, _, hx, hy, size, off = struct.unpack_from('<BBBBHHII', data, 6 + 16 * i)
        if typ == 1:
            hx = hy = 0
        res.append(_dib(data, off, size, (hx, hy)))
    return res


def decode_ani(data):
    assert data[:4] == b'RIFF' and data[8:12] == b'ACON', 'nao e ANI'
    frames, rates, seq = [], None, None
    nsteps, jif = None, 10

    def walk(p, end):
        nonlocal rates, seq, nsteps, jif
        while p + 8 <= end:
            cid = data[p:p + 4]
            sz = struct.unpack_from('<I', data, p + 4)[0]
            body = p + 8
            if cid == b'LIST':
                walk(body + 4, body + sz)
            elif cid == b'anih':
                (_, nfr, nsteps, _, _, _, _, jif, flags) = struct.unpack_from('<9I', data, body)
            elif cid == b'rate':
                rates = list(struct.unpack_from('<%dI' % (sz // 4), data, body))
            elif cid == b'seq ':
                seq = list(struct.unpack_from('<%dI' % (sz // 4), data, body))
            elif cid == b'icon':
                frames.append(decode_cur(data[body:body + sz])[0])
            p = body + sz + (sz & 1)

    walk(12, len(data))
    n = nsteps or len(frames)
    if seq is None:
        seq = list(range(len(frames)))[:n]
    if rates is None:
        rates = [jif] * len(seq)
    return frames, rates, seq, jif


def load(path):
    data = open(path, 'rb').read()
    if data[:4] == b'RIFF':
        frames, rates, seq, _ = decode_ani(data)
        return [(frames[s], r) for s, r in zip(seq, rates)]
    return [(f, 0) for f in decode_cur(data)]
