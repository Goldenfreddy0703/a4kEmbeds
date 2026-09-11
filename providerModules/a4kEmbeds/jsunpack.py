"""P.A.C.K.E.R. javascript unpacker (ported from Otaku / js-beautifier)."""

import binascii
import re


def detect(source):
    mystr = re.search(
        r"eval *\( *function *\( *p *, *a *, *c *, *k *, *e *, *",
        source,
    )
    return mystr is not None


def unpack(source):
    payload, symtab, radix, count = _filterargs(source)
    if count != len(symtab):
        raise UnpackingError("Malformed p.a.c.k.e.r. symtab.")

    try:
        unbase = Unbaser(radix)
    except TypeError:
        raise UnpackingError("Unknown p.a.c.k.e.r. encoding.")

    def lookup(match):
        word = match.group(0)
        return symtab[int(word)] if radix == 1 else symtab[unbase(word)] or word

    def getstring(c, a=radix):
        foo = chr(c % a + 161)
        return foo if c < a else getstring(int(c / a), a) + foo

    payload = payload.replace("\\\\", "\\").replace("\\'", "'")
    p = re.search(r"eval\(function\(p,a,c,k,e.+?String\.fromCharCode\(([^)]+)", source)
    pnew = (
        re.findall(r"String\.fromCharCode\(([^)]+)", source)[0].split("+")[1] == "161"
        if p
        else False
    )

    if pnew:
        for i in range(count - 1, -1, -1):
            payload = payload.replace(getstring(i), symtab[i])
        return _replacejsstrings(_replacestrings(payload))
    source = re.sub(r"\b\w+\b", lookup, payload, flags=re.ASCII)
    return _replacestrings(source)


def _filterargs(source):
    argsregex = r"}\s*\('(.*)',\s*(.*?),\s*(\d+),\s*'(.*?)'\.split\('\|'\)"
    args = re.search(argsregex, source, re.DOTALL).groups()
    try:
        payload, radix, count, symtab = args
        radix = 36 if not radix.isdigit() else int(radix)
        return payload, symtab.split("|"), radix, int(count)
    except ValueError:
        raise UnpackingError("Corrupted p.a.c.k.e.r. data.")


def _replacestrings(source):
    match = re.search(r'var *(_\w+)=\["(.*?)"];', source, re.DOTALL)
    if match:
        varname, strings = match.groups()
        startpoint = len(match.group(0))
        lookup = strings.split('","')
        variable = "%s[%%d]" % varname
        for index, value in enumerate(lookup):
            if "\\x" in value:
                value = value.replace("\\x", "")
                value = binascii.unhexlify(value).decode("ascii")
            source = source.replace(variable % index, '"%s"' % value)
        return source[startpoint:]
    return source


def _replacejsstrings(source):
    match = re.findall(r"\\x([0-7][0-9A-F])", source)
    if match:
        for value in set(match):
            source = source.replace("\\x{0}".format(value), binascii.unhexlify(value).decode("ascii"))
    return source


class Unbaser:
    ALPHABET = {
        62: "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
        95: (
            r' !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            r"[\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
        ),
    }

    def __init__(self, base):
        self.base = base
        if 2 <= base <= 36:
            self.unbase = lambda string: int(string, base)
        else:
            if base < 62:
                self.ALPHABET[base] = self.ALPHABET[62][0:base]
            elif 62 < base < 95:
                self.ALPHABET[base] = self.ALPHABET[95][0:base]
            self.dictionary = dict((cipher, index) for index, cipher in enumerate(self.ALPHABET[base]))
            self.unbase = self._dictunbaser

    def __call__(self, string):
        return self.unbase(string)

    def _dictunbaser(self, string):
        ret = 0
        for index, cipher in enumerate(string[::-1]):
            ret += (self.base ** index) * self.dictionary[cipher]
        return ret


class UnpackingError(Exception):
    pass
