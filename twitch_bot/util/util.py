from PyQt4 import QtGui
from colorsys import hsv_to_rgb, rgb_to_hsv
import re

def hue_65535_to_365(val_65535):
    ratio = float(val_65535) / float(65535)
    val_359 = int(359 * ratio)

    return val_359

def hue_qcolor(hue_color):
    hue = hue_65535_to_365(hue_color)
    return QtGui.QColor.fromHsv(hue, 255, 128)

def hue_to_rgb(hue):
    hsv_to_rgb_res = hsv_to_rgb(hue, 1.0, 1.0)

    return map(lambda x: int(x * 255), hsv_to_rgb_res)

def hue_to_hex(hue):
    return rgb_to_hex(hue_to_rgb(hue))

def rgb_to_hex(rgb):
    converted = map(lambda x: str(hex(x))[2:].zfill(2), rgb)

    return "#%s%s%s" % tuple(converted)

def hex_to_rgb(hex):
    """
    assumes hexs string #FFFFFF
    """
    split = re.findall('..', hex[1:])

    return tuple(int('0x{}'.format(x), 16) for x in split)

def rgb_to_hsv(rgb):
    ratio_rgb = (float(x) / 255.0 for x in rgb)

    return rgb_to_hsv(*ratio_rgb)

def hex_to_hsv(hex):
    rgb = hex_to_rgb(hex)