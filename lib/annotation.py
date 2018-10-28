"""
Copyright (c) 2018- Guoxia Wang
mingzilaochongtu at gmail com

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, subject to the following conditions:         

The above copyright notice and this permission notice shall be included in 
all copies or substantial portions of the Software.

The Software is provided "as is", without warranty of any kind.
"""

from collections import namedtuple
from abc import ABCMeta, abstractmethod
import json
import datetime
import os
import numpy as np


# A point in a polygon
Point = namedtuple('Point', ['x', 'y'])

def enum(*args):
    enums = dict(zip(args, range(len(args))))
    return type('Enum', (), enums)

# Type of an object
AnnObjectType = enum('INSTANCE', 'OCCLUSION_BOUNDARY')

# Abstract base class for annotation objects
class AnnObject:
    __metaclass__ = ABCMeta

    def __init__(self, objType):
        self.objectType = objType
        
        # If deleted or not
        self.deleted  = 0
        # If verified or not
        self.verified = 0
        # The date string
        self.date     = ""
        # The username
        self.user     = ""
        # Draw the object
        # Not read from or written to JSON
        # Set to False if deleted object
        # Might be set to False by the application for other reasons
        self.draw     = True

    @abstractmethod
    def __str__(self): pass

    @abstractmethod
    def fromJsonText(self, jsonText, objId=-1): pass

    @abstractmethod
    def toJsonText(self): pass

    def updateDate( self ):
        self.date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Mark the object as deleted
    def delete(self):
        self.deleted = 1
        self.draw    = False

# Class that contains the information of a single annotated object as polygon
class AnnInstance(AnnObject):
    # Constructor
    def __init__(self):
        AnnObject.__init__(self, AnnObjectType.INSTANCE)
        # the polygon as list of points
        self.polygon    = []
        # the object ID
        self.id         = -1
        # the label
        self.label      = ""
        # temporary color for draw label
        self.color      = None

    def __str__(self):
        polyText = ""
        if self.polygon:
            # TODO
            pass
        else:
            polyText = "none"
        text = "Object: {} - {}".format( self.label , polyText )
        return text

    def fromJsonText(self, jsonText, objId):
        self.id = objId
        self.label = str(jsonText['label'])
        self.polygon = []
        for polygon in jsonText['polygon']:
            polygon = np.array(polygon).reshape((int(len(polygon)/2), 2))
            newPoly = []
            for i in range(polygon.shape[0]):
                newPoly.append(Point(polygon[i][0], polygon[i][1]))
            self.polygon.append(newPoly)
        if ('deleted' in jsonText.keys()):
            self.deleted = jsonText['deleted']
        else:
            self.deleted = 0
        if ('verified' in jsonText.keys()):
            self.verified = jsonText['verified']
        else:
            self.verified = 1
        if ('user' in jsonText.keys()):
            self.user = jsonText['user']
        else:
            self.user = ''
        if ('date' in jsonText.keys()):
            self.date = jsonText['date']
        else:
            self.date = ''
        if (self.deleted == 1):
            self.draw = False
        else:
            self.draw = True

    def toJsonText(self):
        objDict = {}
        objDict['label'] = self.label
        objDict['id'] = self.id
        objDict['deleted'] = self.deleted
        objDict['verified'] = self.verified
        objDict['user'] = self.user
        objDict['date'] = self.date
        objDict['polygon'] = []
        for poly in self.polygon:
            newPoly = []
            for pt in poly:
                newPoly.append(pt.x)
                newPoly.append(pt.y)
            objDict['polygon'].append(newPoly)

        return objDict

# Class that contains the information of a single annotated object as polygon
class AnnBoundary(AnnObject):
    # Constructor
    def __init__(self):
        AnnObject.__init__(self, AnnObjectType.OCCLUSION_BOUNDARY)
        # the polygon as list of points
        self.polygon    = []

    def __str__(self):
        polyText = ""
        if self.polygon:
            # TODO
            pass
        else:
            polyText = "none"
        text = "Boundary: {}".format(polyText )
        return text

    def fromJsonText(self, jsonText, objId = -1):
        self.polygon = []
        for polygon in jsonText['polygon']:
            polygon = np.array(polygon).reshape((int(len(polygon)/2), 2))
            newPoly = []
            for i in range(polygon.shape[0]):
                newPoly.append(Point(polygon[i][0], polygon[i][1]))
            self.polygon.append(newPoly)
        if ('deleted' in jsonText.keys()):
            self.deleted = jsonText['deleted']
        else:
            self.deleted = 0
        if ('verified' in jsonText.keys()):
            self.verified = jsonText['verified']
        else:
            self.verified = 1
        if ('user' in jsonText.keys()):
            self.user = jsonText['user']
        else:
            self.user = ''
        if ('date' in jsonText.keys()):
            self.date = jsonText['date']
        else:
            self.date = ''
        if (self.deleted == 1):
            self.draw = False
        else:
            self.draw = True

    def toJsonText(self):
        objDict = {}
        objDict['deleted'] = self.deleted
        objDict['verified'] = self.verified
        objDict['user'] = self.user
        objDict['date'] = self.date
        objDict['polygon'] = []
        for poly in self.polygon:
            newPoly = []
            for pt in poly:
                newPoly.append(pt.x)
                newPoly.append(pt.y)
            objDict['polygon'].append(newPoly)

        return objDict

# The annotation of a whole image (doesn't support mixed annotations)
class Annotation:
    # Constructor
    def __init__(self, objType=AnnObjectType.INSTANCE):
        # the width of that image and thus of the label image
        self.imgWidth  = 0
        # the height of that image and thus of the label image
        self.imgHeight = 0
        # the list of objects
        self.objects = []
        # the boundaries
        self.boundaries = None
        assert objType in AnnObjectType.__dict__.values()
        self.objectType = objType

    def fromJsonText(self, jsonText):
        jsonDict = json.loads(jsonText)
        self.imgWidth  = int(jsonDict['imgWidth'])
        self.imgHeight = int(jsonDict['imgHeight'])
        self.objects   = []
        for objId, objIn in enumerate(jsonDict['objects']):
            if (self.objectType == AnnObjectType.INSTANCE):
                obj = AnnInstance()
            obj.fromJsonText(objIn, objId)
            self.objects.append(obj)
        self.boundaries = None
        if ('boundaries' in jsonDict.keys()):
            self.boundaries = AnnBoundary()
            self.boundaries.fromJsonText(jsonDict['boundaries'])

    def toJsonText(self):
        jsonDict = {}
        jsonDict['imgWidth'] = self.imgWidth
        jsonDict['imgHeight'] = self.imgHeight
        jsonDict['objects'] = []
        for obj in self.objects:
            objDict = obj.toJsonText()
            jsonDict['objects'].append(objDict)
        if (self.boundaries):
            jsonDict['boundaries'] = self.boundaries.toJsonText()
  
        jsonText = json.dumps(jsonDict, default=lambda o: o.__dict__, sort_keys=True, indent=4)
        return jsonText

    # Read a json formatted polygon file and return the annotation
    def fromJsonFile(self, jsonFile):
        if not os.path.isfile(jsonFile):
            print('Given json file not found: {}'.format(jsonFile))
            return
        with open(jsonFile, 'r') as f:
            jsonText = f.read()
            self.fromJsonText(jsonText)

    def toJsonFile(self, jsonFile):
        with open(jsonFile, 'w') as f:
            f.write(self.toJsonText())
