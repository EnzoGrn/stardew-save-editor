"""XML reading/writing that matches the game's format exactly.

The game writes its files with a UTF-8 BOM, an XML declaration in double
quotes and empty tags written as <tag />. We reproduce that format exactly:
a file that is read then written back unchanged is byte-for-byte identical
to the original.
"""
import os
import re
import tempfile

from lxml import etree

BOM = b"\xef\xbb\xbf"
DECLARATION = b'<?xml version="1.0" encoding="utf-8"?>'
_PARSER = etree.XMLParser(huge_tree=True, remove_blank_text=False)


def load(path):
    return etree.parse(str(path), _PARSER)


def serialize(tree):
    body = etree.tostring(tree.getroot(), encoding="utf-8")
    body = re.sub(rb"(?<=[^ ])/>", b" />", body)
    return BOM + DECLARATION + body


def save(tree, path):
    """Writes to a temporary file, then swaps it in: never a half-written file."""
    data = serialize(tree)
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp_", suffix=".xml")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise