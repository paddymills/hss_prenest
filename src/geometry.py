
from django.template import Engine, Context
from django.conf import settings
from datetime import datetime

import codecs
import json
import os
import math
import threading

XML_IMPORT_EXEC = r"\\HSSIENG\SNDataDev\__oys\bin\SNImportXML\SNImportXML.exe"

_dir = r'\\HSSIENG\SNDataDev\__oys\SNImportXML'
_input_dir = os.path.join(_dir, "Input")
_error_dir = os.path.join(_dir, "Error")
_prenest = r"\\hssieng\SNDataDev\PARTS\Prenesting"
templates = 'xml'

settings.configure()
engine = Engine(dirs=[
    os.path.join(os.path.dirname(__file__), templates),
])

known_alias = {
    'PART': 'PartName',
    'WO': 'WorkOrderNumber',
    'DWG': 'DrawingNumber',
    'GRADE': 'Material',
    'THK': 'Thickness',
    'QTY': 'Quantity',
    'JOB': 'PartData1',
    'SHIPMENT': 'PartData2',
    'MATERIALMASTER': 'PartData10',
    'MM': 'PartData10',
}

dim_alias = {
    'WID': 'width',
    'WIDTH': 'width',
    'LEN': 'length',
    'LENGTH': 'length',
}


def run_xml_import():
    def main_thread():
        os.system(XML_IMPORT_EXEC + " PROCESSXML")

    def progress_thread():
        while 1:
            inbound = len(os.listdir(_input_dir))
            errors = int(len(os.listdir(_error_dir)) / 2)
            print("\rInbound: {}\tErrors: {}".format(inbound, errors), end='')

            if inbound == 0:
                break
        print("\n")

    # create thraeds
    main = threading.Thread(target=main_thread)
    progress = threading.Thread(target=progress_thread)

    # start threads
    main.start()
    progress.start()

    # join (wait to end) threads
    main.join()
    progress.join()


def load_defaults():
    with open(os.path.join(os.path.dirname(__file__), templates, 'defaults.json'), 'r') as defaults:
        return json.loads(defaults.read())


def mid_ordinate(length, radius):
    half_angle = math.degrees(math.asin(length / (2 * radius)))
    mid = radius * (1 - math.cos(math.radians(half_angle)))

    return mid, half_angle


class Part:

    def __init__(self, prenest=False, **kwargs):
        self.__attrs = load_defaults()
        self.__dims = {}
        self.__geo = {}
        for k, v in kwargs.items():
            self.attr(k, v)
        if prenest:
            self.attr('PartSavePath', _prenest)

        if self.__dims:
            self.rect(self.__dims["width"], self.__dims["length"])

    def attr(self, attr, val):
        attr_ucase = attr.upper()

        if attr in self.__attrs.keys():
            self.__attrs[attr] = val
        elif attr_ucase in known_alias.keys():
            if type(known_alias[attr_ucase]) is str:
                self.__attrs[known_alias[attr_ucase]] = val
            else:  # if functions are paired with keys in known_alias
                getattr(self, known_alias[attr_ucase])(val)
        elif attr_ucase in [x.upper() for x in self.__attrs.keys()]:
            self.set_attr(
                {x.upper(): x for x in self.__attrs.keys()}[attr_ucase], val)
        elif attr_ucase in dim_alias.keys():
            self.__dims[dim_alias[attr_ucase]] = val
        else:
            print('Item', attr, 'not recognized as valid attribute')

    def geometry(self, process, geometry, **kwargs):
        _geometry = geometry.copy()
        for k, v in kwargs.items():
            if k in _geometry.keys():
                _geometry[k] = v
            else:
                print(f'Key {k} not in {process} geometry list')
        for k, v in _geometry.items():
            if v == '':
                print(f'No value for {process} :: {k}')
                break
        else:
            if process not in self.__geo.keys():
                self.__geo[process] = []
            self.__geo[process].append(_geometry)

    def rect(self, width, length):
        _temp = [
            {'end_x': length},  # bottom line
            {'start_y': width, 'end_y': width, 'end_x': length},  # top line
            {'end_y': width},  # left side
            {'start_x': length, 'end_y': width, 'end_x': length}  # right side
        ]

        for args in _temp:
            self.geometry(Process.CUT, Geometry.LINE, **args)

    def rect_mid_ord(self, width, length, mid):
        rad = ((length / 2) ** 2 + mid ** 2) / (2 * mid)
        self.rect_rad(length, width, rad)

    def rect_rad(self, width, length, rad, create_ends=True):
        if rad >= 0:
            CENTRAL_ANGLE = 90
        else:
            CENTRAL_ANGLE = 180 + 90

        mid, half_angle = mid_ordinate(length, rad)
        rad = float(rad)
        _ends = [
            {'end_y': width},
            {'start_x': length, 'end_x': length, 'end_y': width}
        ]
        _sides = [
            {'x': length / 2,
                'y': mid - rad,
                'rad': rad,
                'start': CENTRAL_ANGLE - half_angle,
                'end': CENTRAL_ANGLE + half_angle,
             },
            {
                'x': length / 2,
                'y': mid - rad + width,
                'rad': rad,
                'start': CENTRAL_ANGLE - half_angle,
                'end': CENTRAL_ANGLE + half_angle,
            }
        ]

        if create_ends:
            for args in _ends:
                self.geometry(Process.CUT, Geometry.LINE, **args)
        for args in _sides:
            self.geometry(Process.CUT, Geometry.ARC, **args)

    @property
    def context(self):
        self.__attrs['geometry'] = self.__geo
        if not self.__attrs['DueDate']:
            self.__attrs['DueDate'] = datetime.today().strftime('%Y-%m-%d')
        return Context(self.__attrs)

    @property
    def xml_file(self):
        return os.path.join(_input_dir, (self.__attrs['PartName'] + '.xml'))

    def generate_xml(self):
        if not self.__geo:
            print('No part geometry supplied')
        else:
            codecs.open(self.xml_file, 'w', 'utf-8').write(
                engine.get_template('base.xml').render(self.context)
            )


class Process:

    CUT = 'CUT'
    TEXT = 'NOCUT'
    LEADIN = 'CUTLEADIN'
    NOKERF = 'NOKERF'
    MARK = 'PRIMARYMARK'


class Geometry:

    LINE = {
        'template': 'line.xml',
        'start_x': 0,
        'start_y': 0,
        'end_x': 0,
        'end_y': 0
    }
    ARC = {
        'template': 'arc.xml',
        'x': '',
        'y': '',
        'rad': 0,
        'start': '',
        'end': '',
        'ccw': 'true'
    }
    HOLE = {
        'template': 'circle.xml',
        'x': '',
        'y': '',
        'dia': '',
    }
    TEXT = {
        'template': 'note.xml',
        'x': '',
        'y': '',
        'text': '',
        'angle': 0,
        'size': 2
    }
    POINT = {
        'template': 'point.xml',
        'x': '',
        'y': ''
    }
