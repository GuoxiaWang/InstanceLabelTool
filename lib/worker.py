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
from PyQt4 import QtCore, QtGui
import numpy as np
import cv2
import os
import getpass

from edgelink import edgelink

from annotation import Point, Annotation, AnnBoundary

class ConvertToBoundariesWorker(QtCore.QObject):
    """
    Make a new thread instance to convert to boundaries 
    from a segment map
    """
    finishedSignal = QtCore.pyqtSignal(list)
    def __init__(self, objects=None, height=0, width=0):
        QtCore.QObject.__init__(self)
        self.objects = objects
        self.segmentMap = np.zeros((height, width), np.uint8)

    def setObjects(self, objects):
        self.objects = objects

    def setSegmentMap(self, height, width):
        self.segmentMap = np.zeros((height, width), np.uint8)

    # Segment map convert to boundary list
    def convertToBoundaries(self):
        # First, we fill all labels to numpy ndarray
        count = 1
        for obj in self.objects:
            for poly in obj.polygon:
                pts = []
                for pt in poly:
                    pts.append([pt.x, pt.y])
                pts = np.around(pts).astype(np.int32)
                cv2.fillPoly(self.segmentMap, [pts], count)
            count += 1

        # Second, we convert to boundary map from segment map
        edgeMap = self.segmentationMapToBoundaryMap(self.segmentMap)
        # Third, we get edge fragments
        edgelist, edgeim, etype = edgelink(edgeMap)
        polygon = []
        for edge in edgelist:
            if (len(edge) < 5):
                continue
            # Auto correct occlusion boundary direction
            if (self.isNeedReverse(edge)):
                edge.reverse()
            # Convert to QPolygonF
            poly = []
            for pt in edge:
                point = Point(pt[1], pt[0])
                poly.append(point)
            polygon.append(poly)
        self.finishedSignal.emit(polygon)
        return polygon

    # Label segmentation map to boundary map
    def segmentationMapToBoundaryMap(self, segment):
        height, width = segment.shape
        boundary = np.zeros((2*height+1, 2*width+1), np.uint8)
        # Find vertical direction difference
        edgelsV = (segment[0:-1, :] != segment[1:, :]).astype(np.uint8)
        # Add a zero row
        edgelsV = np.vstack([edgelsV, np.zeros((1, width), dtype=np.uint8)])
        # Find horizontal direction difference
        edgelsH = (segment[:,0:-1] != segment[:, 1:]).astype(np.uint8)
        # Append a zero column
        edgelsH = np.hstack([edgelsH, np.zeros((height, 1), dtype=np.uint8)])

        # Assign to boundary
        boundary[2::2, 1::2] = edgelsV
        boundary[1::2, 2::2] = edgelsH

        # Get boundary
        boundary[2:-1:2, 2:-1:2] = np.maximum(
            np.maximum(edgelsH[0:-1, 0:-1], edgelsH[1:, 0:-1]),
            np.maximum(edgelsV[0:-1, 0:-1], edgelsV[0:-1, 1:]))

        boundary[0, :] = boundary[1, :]
        boundary[:, 0] = boundary[:, 1]
        boundary[-1, :] = boundary[-2, :]
        boundary[:, -1] = boundary[:, -2]

        boundary = boundary[2::2, 2::2]
        return boundary

    # Check one edge occluison direction, and return true if need reverse
    def isNeedReverse(self, edge):
        height, width = self.segmentMap.shape

        step = 3
        posDirCount = 0
        totalCount = len(edge) / step
        for i in range(totalCount):
            idx = i * step
            pt1 = QtCore.QPointF(edge[idx][1], edge[idx][0])
            idx = (i + 1) * step
            if (idx >= len(edge)):
                idx = -1
            pt2 = QtCore.QPointF(edge[idx][1], edge[idx][0])

            line1 = QtCore.QLineF(pt1, pt2)
            line1 = line1.normalVector()
            pt3 = line1.p2()
            pt3.setX(min(max(pt3.x(), 0), width-1))
            pt3.setY(min(max(pt3.y(), 0), height-1))

            pt4 = QtCore.QPointF(line1.x1() - line1.dx(), line1.y1() - line1.dy())
            pt4.setX(min(max(pt4.x(), 0), width-1))
            pt4.setY(min(max(pt4.y(), 0), height-1))
            
            if (self.segmentMap[int(pt3.y()), int(pt3.x())] >=
                self.segmentMap[int(pt4.y()), int(pt4.x())]):
                posDirCount += 1
        ratio = float(posDirCount) / np.ceil(float(totalCount))
        # If ratio greater than the threshold, we dont need to reverse the edge
        if (ratio > 0.3):
            return False
        else:
            return True

class BatchConvertToBoundariesWorker(QtCore.QObject):
    """
    Make a new thread instance to batch convert to occlusion boundary labels
    from instance labels
    """
    updateProgress = QtCore.pyqtSignal(int, str)
    finished = QtCore.pyqtSignal()
    information = QtCore.pyqtSignal(str, str)
    
    # Flag indicate cancel by user
    canceled = False
    # User selected operation
    userOperationResult = -1

    # Mutex and waitcondition
    mutex = QtCore.QMutex()
    waitCondition = QtCore.QWaitCondition()

    def __init__(self, imageList, imageDir, gtExt):
        QtCore.QObject.__init__(self)
        self.imageDir = imageDir
        self.imageList = imageList
        self.gtExt = gtExt

    def stop(self):
        self.canceled = True

    def batchConvertToBoundaries(self):
        overwriteAll = False
        annotation = Annotation()
        worker = ConvertToBoundariesWorker()
        # Convert each image
        for idx, filename in enumerate(self.imageList):
            if (self.canceled):
                break

            # get label json file name
            imageExt = os.path.splitext(filename)[1]
            gtfilename = filename.replace(imageExt, self.gtExt)
            filename = os.path.join(self.imageDir, gtfilename)
            filename = os.path.normpath(filename)

            # Update progress dialog
            self.updateProgress.emit(idx + 1, "Converting {0}".format(gtfilename))

            # Check if label json file exist
            if (not os.path.isfile(filename)):
                text = "{0} not exist. Continue?".format(filename)
                self.mutex.lock()
                self.information.emit("IOError", text)
                self.waitCondition.wait(self.mutex)
                self.mutex.unlock()
                if (self.userOperationResult == QtGui.QMessageBox.Yes):
                    continue
                else:
                    break
                
            try:
                annotation = Annotation()
                annotation.fromJsonFile(filename)
            except StandardError  as e:
                text = "Error parsing labels in {0}. \nContinue?".format(filename)
                self.mutex.lock()
                self.information.emit("IOError", text)
                self.waitCondition.wait(self.mutex)
                self.mutex.unlock()
                if (self.userOperationResult == QtGui.QMessageBox.Yes):
                    continue
                else:
                    break

            # Skip all image of has no instance labels
            if (not annotation.objects):
                continue

            # Check if it has occlusion boundary label
            if (not overwriteAll and annotation.boundaries):
                text = "{0} already exists occlusion boundary labels. Do you want to overwrite?".format(filename)
                self.mutex.lock()
                self.information.emit("Overwrite", text)
                self.waitCondition.wait(self.mutex)
                self.mutex.unlock()
                if (self.userOperationResult == QtGui.QMessageBox.No):
                    continue
                elif (self.userOperationResult == QtGui.QMessageBox.YesToAll):
                    overwriteAll = True

            height = annotation.imgHeight
            width = annotation.imgWidth
            worker.setObjects(annotation.objects)
            worker.setSegmentMap(height, width)
            polygon = worker.convertToBoundaries()

            # Create a new boundary object
            boundaries = AnnBoundary()
            boundaries.polygon = polygon 
            boundaries.deleted = 0
            boundaries.verified = 0
            boundaries.user = getpass.getuser()
            boundaries.updateDate()
            annotation.boundaries = boundaries
            try:
                annotation.toJsonFile(filename)
            except StandardError  as e:
                text = "Error writting labels to {0}. \nContinue?".format(filename)
                self.mutex.lock()
                self.information.emit("IOError", text)
                self.waitCondition.wait(self.mutex)
                self.mutex.unlock()
                if (self.userOperationResult == QtGui.QMessageBox.Yes):
                    continue
                else:
                    break
            
        self.finished.emit()
