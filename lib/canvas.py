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
from PyQt4 import QtGui, QtCore
import getpass
import numpy as np

from annotation import Point, AnnObjectType, AnnInstance, AnnBoundary, Annotation
from worker import ConvertToBoundariesWorker

class Canvas(QtGui.QWidget):
    scrollRequest = QtCore.pyqtSignal(int, int)
    showMessage = QtCore.pyqtSignal(str)
    busyWaiting = QtCore.pyqtSignal(bool)

    def __init__(self, *args, **kwargs):
        super(Canvas, self).__init__(*args, **kwargs)

        # The zoom factor
        self.zoomFactor = 1.0

        # The transparency of the labels over the image
        self.transp = 0.5
        # Temporary zero transparency
        self.transpTempZero = False

        # Redraw Labels
        self.redraw = True
        
        # A point of this poly that is dragged
        self.draggedPt = (-1, -1)
        
        # A polygon that is drawn by the user
        self.drawPoly = QtGui.QPolygonF()
        # The polygons of one object
        self.polygons = []
        
        # The mouse position
        self.mousePos = None
        # The flag of dragging the canvas
        self.draggingCanvas = False
        # The mouse position when dragging the canvas
        self.dragMousePos = None
        # The current object the mouse points to. It's the index in self.annotation.objects
        self.mouseObj = (-1, -1)
        # The current boundary the mouse points to, It's the index in self.annotation.boundaries
        self.mouseBdry = -1
        # The currently selected objects. Their index in self.annotation.objects
        self.selObjs = []

        # Current image as QImage
        self.image = QtGui.QImage()

        # Cache image, if there are no labels changed, we draw cache image
        self.cacheImage = QtGui.QImage()
        self.cacheLabelImage = QtGui.QImage()
        
        # Current selected label
        self.curLabel = ""

        # Current draw label type
        self.curDrawType = AnnObjectType.OCCLUSION_BOUNDARY

        # All annotated objects in current image
        self.annotation = None

        # Change flag
        self.changes = False

        # Occlusion boundary convert thread
        self.convertThread = None

        # A list of toolbar actions that need a closed drawn polygon
        self.actClosedPoly = []
        # A list of toolbar actions that need the selected objects
        self.actSelObj = []
        # A list of toolbar actions that need to save
        self.actChanges = []

        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.WheelFocus)


    # This method is called when redrawing everything
    # Can be manually triggered by self.update()
    def paintEvent(self, event):
        qp = QtGui.QPainter()
        qp.begin(self)
        #qp.setRenderHint(QtGui.QPainter.Antialiasing)
        #qp.setRenderHint(QtGui.QPainter.HighQualityAntialiasing)
        self.drawCanvas(qp)
        qp.end()	
        
        # Forward the paint event
        QtGui.QMainWindow.paintEvent(self, event)

    def drawCanvas(self, qp):
        # Return if no image available
        if self.image.isNull():
            return

        # Save the painters current setting to a stack
        qp.save()
        # Set transformation
        qp.scale(self.zoomFactor, self.zoomFactor)
        qp.translate(self.offsetToCenter())
        # Determine the object ID to highlight
        self.getHighlightedObjectIds()
        if (self.redraw):
            self.drawCacheImage(qp)
            self.redraw = False
        qp.drawImage(0, 0, self.cacheImage)
		# Draw the user drawn polygon
        self.drawPolygons(qp)
        # Draw the label name next to the mouse
        self.drawLabelAtMouse()
        # Restore the saved setting from the stack
        qp.restore()

    def drawCacheImage(self, qp):
        self.cacheImage = QtGui.QImage(self.image.width(), self.image.height(), QtGui.QImage.Format_ARGB32_Premultiplied)
        qp = QtGui.QPainter()
        qp.begin(self.cacheImage)
        # Draw the image first
        qp.drawImage(0, 0, self.image)

        # Redraw label image
        if (self.redraw):
            self.cacheLabelImage = self.drawLabels()

        if (self.cacheLabelImage and not self.transpTempZero):
            qp.save()
            # Define transparency
            qp.setOpacity(self.transp)
            # Draw the overlay image
            qp.drawImage(0, 0, self.cacheLabelImage)
            # Restore settings
            qp.restore()

        if (self.redraw and
            self.curDrawType == AnnObjectType.OCCLUSION_BOUNDARY):
            self.drawOcclusionBoundary(qp)

        qp.end()

    # Draw all polygons of one object
    def drawPolygons(self, qp):
        if (not self.image):
            return

        # The closed polygons
        for poly in self.polygons:
            self.drawPolygon(qp, poly, True)
        
        # If current drawing polygon is empty, do nothing
        if (self.drawPoly.isEmpty()):
            return

        # The current drawing polygon - make a copy
        poly = QtGui.QPolygonF(self.drawPoly)
        poly.append(self.mousePos)

        self.drawPolygon(qp, poly, False)

    # Draw  polygon
    def drawPolygon(self, qp, poly, polygonClosed, fill=True):
        if (not self.image):
            return
        if (poly.isEmpty()):
            return

        # Save the painters current setting to a stack
        qp.save()
        
        # Fill the polygon with semi-transparant color
        if (fill):
            qp.setBrush(QtGui.QBrush(QtGui.QColor(255, 0, 0, 127), QtCore.Qt.SolidPattern))
            qp.setPen(QtCore.Qt.NoPen)
            qp.drawPolygon(poly)

        # Do not fill the polygon
        qp.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))

        # Draw the polygon edges
        polyColor = QtGui.QColor(255, 0, 0)
        qp.setPen(polyColor)
        if (not polygonClosed):
            qp.drawPolyline(poly)
        else:
            qp.drawPolygon(poly)

        # Get the ID of the closest point to the mouse
        closestPt = self.getClosestPoint(poly, self.mousePos, polygonClosed)
        # If a polygon edge is selected, draw in bold
        if (closestPt[0] != closestPt[1]):
            thickPen = QtGui.QPen(polyColor)
            thickPen.setWidth(1.7)
            qp.setPen(thickPen)
            qp.drawLine(poly[closestPt[0]], poly[closestPt[1]])

        # Draw the polygon points
        qp.setPen(polyColor)
        startDrawingPts = 0

        # A bit diffent if not closed
        if (not polygonClosed):
            self.drawPoint(qp, poly.first(), True, closestPt == (0, 0) and poly.size() > 1)
            # Do not draw again
            startDrawingPts = 1

        # The next in red
        for pt in range(startDrawingPts, poly.size()):
            self.drawPoint(qp, poly[pt], False, closestPt == (pt, pt) and polygonClosed)
	
        # Restore QPainter settings from stack
        qp.restore()
        
    def drawPoint(self, qp, pt, isFirst, increaseRadius):
        # The first in green
        if (isFirst):
            qp.setBrush(QtGui.QBrush(QtGui.QColor(0, 255, 0), QtCore.Qt.SolidPattern))
        else:
            qp.setBrush(QtGui.QBrush(QtGui.QColor(255, 0, 0), QtCore.Qt.SolidPattern))

        # Standard radius
        r = 1.2
        # Increase maybe
        if (increaseRadius):
            r *= 1.5
        # Draw
        qp.drawEllipse(pt, r, r)

    # Draw the labels in the given QPainter qp
    # optionally provide a list of labels to ignore
    def drawLabels(self, ignore = []):
        if (self.image.isNull()):
            return
        if (not self.annotation or not self.annotation.objects):
            return

        overlay = QtGui.QImage(self.image.width(), self.image.height(), QtGui.QImage.Format_ARGB32_Premultiplied)
        col = QtGui.QColor(0, 0, 0)
        overlay.fill(col)
        qp = QtGui.QPainter()
        qp.begin(overlay)
        qp.save() 
        
        # The color of the outlines
        qp.setPen(QtGui.QColor('white'))
        # Draw all objects
        for idx, obj in enumerate(self.annotation.objects):
            # Some are flagged to not be drawn, skip them
            if (not obj.draw):
                continue

            # The label of the object
            labelName = obj.label

            # If we ignore this label, ski
            if (labelName in ignore):
                continue
            
            polygon = self.getPolygon(obj)

            # Default drawing
            if (not obj.color):
                obj.color = ((np.random.random((1, 3)))*255).astype(np.int32).tolist()[0]
            col = QtGui.QColor(*obj.color)
            brush = QtGui.QBrush(col, QtCore.Qt.SolidPattern)
            qp.setBrush(brush)
            
            for poly in polygon:
                # Overwrite drawing if this is the highlighted object
                if (idx in self.highlightObjIds):
                    # First clear everything below of the polygon
                    qp.setCompositionMode(QtGui.QPainter.CompositionMode_Clear)
                    qp.drawPolygon(poly)
                    qp.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
                    # Set the drawing to a special pattern
                    brush = QtGui.QBrush(col, QtCore.Qt.DiagCrossPattern)
                    qp.setBrush(brush)

                qp.drawPolygon(poly)

        # Draw outline of selected object dotted
        brush = QtGui.QBrush(QtCore.Qt.NoBrush)
        qp.setBrush(brush)
        qp.setPen(QtCore.Qt.DashLine)
        for idx in self.highlightObjIds:
            polygon = self.getPolygon(self.annotation.objects[idx])
            for poly in polygon:
                qp.drawPolygon(poly)

        # Restore settings
        qp.restore()
        qp.end()
        
        return overlay

    # Draw the label name next to the mouse
    def drawLabelAtMouse(self):
        # Nothing to do without a highlighted object
        if (not self.highlightObjIds):
            return
        # Also we do not want to draw the label, if we have a draw polygon
        if (not self.drawPoly.isEmpty()):
            return
        # Nothing to do when the mouse leave the image area
        if (self.mouseOutsideImage):
            return

        # Save QPainter setting to stack
        qp = QtGui.QPainter()
        qp.begin(self)
        qp.save()

        # Get the mouse position
        cursor = QtGui.QCursor()
        pos = cursor.pos()
        mouse = QtGui.QWidget.mapFromGlobal(self, pos)

        # The text that is written next to the mouse
        mouseText = self.annotation.objects[self.highlightObjIds[-1]].label
        # Where to write the text
        # The location in the image (if we are at the top we want to write below of the mouse)
        off = 36
        if (mouse.y() - off > 0 and self.mousePos.y() - off > 0):
            top = mouse.y() - off
            btm = mouse.y()
            vAlign = QtCore.Qt.AlignTop
        else:
            # The height of the cursor
            off += 10
            top = mouse.y()
            btm = mouse.y() + off
            vAlign = QtCore.Qt.AlignBottom

        # Here we can draw
        rect = QtCore.QRect()
        rect.setTopLeft(QtCore.QPoint(mouse.x() - 100, top))
        rect.setBottomRight(QtCore.QPoint(mouse.x() + 100, btm))

        # The color
        qp.setPen(QtGui.QColor('white'))
        # The font to use
        font = QtGui.QFont('Helvetica [Cronyx]', 12, QtGui.QFont.DemiBold)
        qp.setFont(font)
        # Non-transparent
        qp.setOpacity(1)
        # Draw the text, horizontally centered
        qp.drawText(rect, QtCore.Qt.AlignHCenter | vAlign, mouseText)
        
        # Restore settings
        qp.restore()
        qp.end()

    # Draw a arrow at given point and direction
    # pt: arrow center point coordinate
    # dx, dy: arrow direction, unit vector
    # arrowLen: arrow length
    # color: arrow edge and fill color
    # fill: whether fill arrow or not
    # front: whether arrow center at head or rear
    def drawArrow(self, qp, pt, dx, dy, arrowLen, color=None, fill=True, front=True):
        cos = 0.866
        sin = 0.500
        cos2 = 0.500
        sin2 = 0.866
        if (front):
            x = pt.x()
            y = pt.y()
        else:
            x = pt.x() + cos * arrowLen * dx
            y = pt.y() + cos * arrowLen * dy

        # calculate Point1 coordinate
        x1 = x - arrowLen * (dx * cos + dy * -sin)
        y1 = y - arrowLen * (dx * sin + dy * cos)

        # calculate Point2 coordinate
        x2 = x - arrowLen * (dx * cos + dy * sin)
        y2 = y - arrowLen * (dx * -sin + dy * cos)

        # calculate Point3 coordinate
        x3 = x1 + 0.577 * arrowLen * (dx * cos2 + dy * -sin2)
        y3 = y1 + 0.577 * arrowLen * (dx * sin2 + dy * cos2)

        pt = QtCore.QPointF(x, y)
        pt1 = QtCore.QPointF(x1, y1)
        pt2 = QtCore.QPointF(x2, y2)
        pt3 = QtCore.QPointF(x3, y3)

        # Save setting
        qp.save()
        if (color):
            col = QtGui.QColor(*color)
            qp.setPen(col)
            if (fill):
                qp.setBrush(QtGui.QBrush(col, QtCore.Qt.SolidPattern))
            else:
                qp.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))

        # Draw arrow polygon
        poly = QtGui.QPolygonF()
        poly.append(pt)
        poly.append(pt1)
        poly.append(pt3)
        poly.append(pt2)
        qp.drawPolygon(poly)

        # Restore setting
        qp.restore()

    # Draw Occlusion boundary
    def drawOcclusionBoundary(self, qp):
        if (self.image.isNull()):
            return
        if (not self.annotation or not self.annotation.boundaries):
            return
        qp.save()
        # we draw an arrow every arrowDistance pixel
        arrowDistance = 5
        boundaries = self.getPolygon(self.annotation.boundaries)
        for idx, boundary in enumerate(boundaries):
            # If a polygon edge is selected, draw in bold
            color = (255, 0, 0)
            if (idx == self.mouseBdry):
                color = (0, 255, 0)
            thickPen = QtGui.QPen(QtGui.QColor(*color))
            thickPen.setWidth(1.7)
            qp.setPen(thickPen)
            qp.drawPolyline(boundary)

            thickPen.setWidth(1)
            qp.setPen(thickPen)
            for i in range(len(boundary) / arrowDistance):
                idx = i * arrowDistance
                pt1 = boundary[idx]
                idx = (i + 1) * arrowDistance
                if (idx >= len(boundary)):
                    idx = -1
                pt2 = boundary[idx]
                midPt = (pt1 + pt2) / 2.0
                unitVector = QtCore.QLineF(pt1, pt2).unitVector()
                unitVector = unitVector.normalVector()
                self.drawArrow(qp, midPt, unitVector.dx(), unitVector.dy(), 5, color=color, fill=True, front=False)
        qp.restore()

    # Determine the highlighted object for drawing
    def getHighlightedObjectIds(self):
        self.highlightObjIds = []
        # Without labels we cannot do so
        if (not self.annotation):
            return
        # If available set the selected objects
        self.highlightObjIds = self.selObjs
        if (not self.highlightObjIds and 
            (self.drawPoly.isEmpty() and not self.polygons) and
            self.mouseObj[0] >= 0):
            self.highlightObjIds = [self.mouseObj[0]]
        
    def sizeHint(self):
        return self.minimumSizeHint()

    def minimumSizeHint(self):
        if (self.image):
            return self.zoomFactor * self.image.size()
        return super(Canvas, self).minimumSizeHint()

    # Update mouse position
    def updateMousePos(self, pt):
        self.mousePos = self.transformPos(pt)
        self.mouseOutsideImage = not self.image.rect().contains(self.mousePos.toPoint())
        self.mousePos.setX(max(self.mousePos.x(), 0.))
        self.mousePos.setY(max(self.mousePos.y(), 0.))
        self.mousePos.setX(min(self.mousePos.x(), self.image.rect().right()))
        self.mousePos.setY(min(self.mousePos.y(), self.image.rect().bottom()))


    # Mouse wheel scrolled
    def wheelEvent(self, event):
        deltaDegree = event.delta() / 8 # Ratation in degree
        deltaSteps = deltaDegree / 15 # Usually one step on the mouse is 15 degrees

        self.zoomFactor += deltaSteps * 0.05
        self.zoomFactor = max(self.zoomFactor, 0.1)
        self.zoomFactor = min(self.zoomFactor, 10)
        self.adjustSize()
        self.update()

    # Mouse moved
    def mouseMoveEvent(self, event):
        if (self.image.isNull()):
            return

        self.updateMousePos(event.posF()) 
        if (self.curDrawType == AnnObjectType.INSTANCE):
            if (self.draggedPt[0] >= 0):
                # Update the dragged point
                pt = QtCore.QPointF(self.polygons[self.draggedPt[0]][self.draggedPt[1]])
                self.polygons[self.draggedPt[0]].replace(self.draggedPt[1], self.mousePos)
                valid = self.checkPolygonValidation(self.polygons[self.draggedPt[0]])
                if (not valid):
                    self.polygons[self.draggedPt[0]].replace(self.draggedPt[1], pt)
                else:
                    self.redraw = True

                # If the polygon is the polygon of the selected object
                # update the object polygon
                if (valid and self.selObjs):
                    obj = self.annotation.objects[self.selObjs[-1]]
                    obj.polygon[self.draggedPt[0]][self.draggedPt[1]] = Point(self.mousePos.x(), self.mousePos.y())
                    self.setChanges()


        elif (self.curDrawType == AnnObjectType.OCCLUSION_BOUNDARY):
            pass

        # Drag canvas
        if (self.draggingCanvas and event.buttons() == QtCore.Qt.LeftButton):
            offset = event.globalPos() - self.dragMousePos
            self.scrollRequest.emit(offset.x(), offset.y())
            self.dragMousePos = event.globalPos()

        # Update the object selected by the mouse
        self.updateMouseObject()

        # Redraw
        self.update()

    # Mouse button pressed
    def mousePressEvent(self, event):
        shiftPressed = event.modifiers() & QtCore.Qt.ShiftModifier
        self.updateMousePos(event.posF())
        if (event.button() == QtCore.Qt.LeftButton):
            if (self.curDrawType == AnnObjectType.INSTANCE):
                if (self.drawPoly.isEmpty() and len(self.polygons) > 0):
                    closestPt = self.getClosestPointFromPolygons(self.polygons, self.mousePos)
                    if (shiftPressed):
                        # Delete point of polygon
                        idxPoly = -1
                        if (closestPt[0] >= 0):
                            idxPoly = closestPt[0]
                        else:
                            for idx, poly in enumerate(self.polygons):
                                if (poly.containsPoint(self.mousePos, QtCore.Qt.OddEvenFill)):
                                    idxPoly = idx
                                    break
                        # If closestPt[1] == closestPt[2] == -1, we delete the last one point of the polygon
                        # Otherwise we delete the closest point to the mouse cursor
                        if (idxPoly >= 0 and closestPt[1] == closestPt[2]):
                            del self.polygons[idxPoly][closestPt[1]]
                            clearFlag = len(self.polygons[idxPoly]) == 2 or not self.polygons[idxPoly]
                            # If the polygon is the polygon of the selected object, update the object
                            if (self.selObjs):
                                self.setChanges()
                                obj = self.annotation.objects[self.selObjs[-1]]
                                del obj.polygon[idxPoly][closestPt[1]]
                                if (clearFlag):
                                    del obj.polygon[idxPoly]
                                    del self.polygons[idxPoly]
                                if (not obj.polygon):
                                    del self.annotation.objects[self.selObjs[-1]]
                                    del self.selObjs[-1]
                                    self.mouseObj = (-1, -1)
                            elif (clearFlag):
                                del self.polygons[idxPoly]

                            # Redraw labels
                            self.redraw = True

                    elif (self.drawPoly.isEmpty()):
                        # If we got a point, we make it dragged
                        if (closestPt[1] == closestPt[2]):
                            self.draggedPt = (closestPt[0], closestPt[1])
                        # If we got an edge, we insert a point and make it dragged
                        else:
                            self.polygons[closestPt[0]].insert(closestPt[2], self.mousePos)
                            self.draggedPt = (closestPt[0], closestPt[2])

                            # Redraw labels
                            self.redraw = True

                            # If the polygon is the polygon of the selected object, update the object
                            if (self.selObjs):
                                self.setChanges()
                                obj = self.annotation.objects[self.selObjs[-1]]
                                obj.polygon[closestPt[0]].insert(closestPt[2], Point(self.mousePos.x(), self.mousePos.y()))

            elif (self.curDrawType == AnnObjectType.OCCLUSION_BOUNDARY):
                pass

        # Handle the dragging canvas event
        if (self.draggingCanvas):
            self.dragMousePos = event.globalPos()

        # Redraw
        self.update()


    # Mouse button released
    def mouseReleaseEvent(self, event):
        ctrlPressed = event.modifiers() & QtCore.Qt.ControlModifier
        altPressed = event.modifiers() & QtCore.Qt.AltModifier
        shiftPressed = event.modifiers() & QtCore.Qt.ShiftModifier
        
        if (self.draggingCanvas):
            return

        # Handle left click
        if (event.button() == QtCore.Qt.LeftButton):
            if (self.curDrawType == AnnObjectType.INSTANCE):
                if (ctrlPressed):
                    # Make the current mouse object the selected and process the selection
                    self.selectObject()
                elif (self.draggedPt[0] >= 0):
                    self.draggedPt = (-1, -1)
                else:
                    # If the mouse would close the poly make sure to do so
                    if (self.ptClosesPoly()):
                        if (self.checkClose()):
                            self.closePolygon()
                    elif (not shiftPressed):
                        if (self.checkPolygonValidation(self.drawPoly, polygonClosed = False, mousePos = self.mousePos)
                                and len(self.selObjs) <= 1):
                            self.addPtToPoly(self.mousePos)

            elif (self.curDrawType == AnnObjectType.OCCLUSION_BOUNDARY):
                boundaries = self.getPolygon(self.annotation.boundaries)
                for idx, boundary in enumerate(boundaries):
                    # Get the ID of the closest point to the mouse
                    closestPt = self.getClosestPoint(boundary, self.mousePos, polygonClosed=False)
                    if (closestPt[0] != -1):
                        self.redraw = True
                        self.annotation.boundaries.polygon[idx].reverse()
                        self.setChanges()
                        break

        # Quickly delete the last added point of current polygon
        elif (event.button() == QtCore.Qt.RightButton):
            if (self.curDrawType == AnnObjectType.INSTANCE):
                if (len(self.drawPoly) > 0):
                    del self.drawPoly[-1]

            elif (self.curDrawType == AnnObjectType.OCCLUSION_BOUNDARY):
                pass

        # Redraw
        self.update()

    # Update the object that is selected by the current mouse cursor
    def updateMouseObject(self):
        if (self.curDrawType == AnnObjectType.INSTANCE):
            oldMouseObj = self.mouseObj
            self.mouseObj = (-1, -1)
            if (not self.annotation or not self.annotation.objects or not self.mousePos):
                return 
            for idx in reversed(range(len(self.annotation.objects))):
                obj = self.annotation.objects[idx]
                if (obj.draw):
                    polygons = self.getPolygon(obj)
                    found = False
                    for k, poly in enumerate(polygons):
                        if (poly.containsPoint(self.mousePos, QtCore.Qt.OddEvenFill)):
                            self.mouseObj = (idx, k)
                            found = True
                            break
                    if (found):
                        break
            if (self.mouseObj != oldMouseObj):
                self.redraw = True

        elif (self.curDrawType == AnnObjectType.OCCLUSION_BOUNDARY):
            oldMouseBdry = self.mouseBdry
            self.mouseBdry = -1
            if (not self.annotation or not self.annotation.boundaries or not self.mousePos):
                return
            boundaries = self.getPolygon(self.annotation.boundaries)
            for idx, boundary in enumerate(boundaries):
                # Get the ID of the closest point to the mouse
                closestPt = self.getClosestPoint(boundary, self.mousePos, polygonClosed=False)
                if (closestPt[0] != -1):
                    self.mouseBdry = idx
                    break
            if (self.mouseBdry != oldMouseBdry):
                self.redraw = True

    def keyPressEvent(self, event):
        key = event.key()
        if (key == QtCore.Qt.Key_Control):
            QtGui.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        elif (key == QtCore.Qt.Key_Space):
            QtGui.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.OpenHandCursor))
            self.draggingCanvas = True
        elif (key == QtCore.Qt.Key_W):
            self.scrollRequest.emit(0, 5)
        elif (key == QtCore.Qt.Key_S):
            self.scrollRequest.emit(0, -5)
        elif (key == QtCore.Qt.Key_A):
            self.scrollRequest.emit(5, 0)
        elif (key == QtCore.Qt.Key_D):
            self.scrollRequest.emit(-5, 0)
        elif (key == QtCore.Qt.Key_Q):
            if (self.checkClose()):
                self.closePolygon()
                self.update()
        elif (key == QtCore.Qt.Key_0):
            self.transpTempZero = True
            self.redraw = True
            self.update()

    def keyReleaseEvent(self, event):
        key = event.key()
        if (key == QtCore.Qt.Key_Control):
            QtGui.QApplication.restoreOverrideCursor()
        if (key == QtCore.Qt.Key_Space):
            QtGui.QApplication.restoreOverrideCursor()
            self.draggingCanvas = False
        elif (key == QtCore.Qt.Key_0):
            self.transpTempZero = False
            self.redraw = True
            self.update()

    def offsetToCenter(self):
        s = self.zoomFactor
        area = super(Canvas, self).size()
        w, h = self.image.width() * s, self.image.height() * s
        aw, ah = area.width(), area.height()

        x = (aw - w) / (2 * s) if aw > w else 0
        y = (ah - h) / (2 * s) if aw > h else 0
        return QtCore.QPointF(x, y)

    def transformPos(self, point):
        return point / self.zoomFactor - self.offsetToCenter() 


    def ptClosesPoly(self):
        if (self.drawPoly.isEmpty()):
            return False
        closestPt = self.getClosestPoint(self.drawPoly, self.mousePos, False)
        return closestPt == (0, 0)

    # Get distance between tow points
    def ptDist(self, pt1, pt2):
        # A line between both
        line = QtCore.QLineF(pt1, pt2)
        # Length
        return line.length()

    # Get the point/edge index within the given polygon that is close to the given point
    # Returns (-1, -1) if none is close enough
    # Returns (i, i) if the point with index i is closed
    # Returns (i, i+1) if the edge from points i to i+1 is closest
    def getClosestPoint(self, poly, pt, polygonClosed = True):
        closest = (-1, -1)
        if (not poly or not pt):
            return closest
        distTh    = 4.0
        dist      = 1e9 # should be enough
        for i in range(poly.size()):
            curDist = self.ptDist(poly[i], pt)
            if curDist < dist:
                closest = (i, i)
                dist = curDist
        # Close enough?
        if (dist <= distTh):
            return closest

        # Otherwise see if the polygon is closed, but a line is close enough
        if (polygonClosed and poly.size() >= 2):
            for i in range(poly.size()):
                pt1 = poly[i]
                j = i+1
                if (j == poly.size()):
                    j = 0
                pt2 = poly[j]
                edge = QtCore.QLineF(pt1, pt2)
                normal = edge.normalVector()
                normalThroughMouse = QtCore.QLineF(pt.x(), pt.y(), pt.x() + normal.dx(), pt.y() + normal.dy())
                intersectionPt = QtCore.QPointF()
                intersectionType = edge.intersect(normalThroughMouse, intersectionPt)
                if (intersectionType == QtCore.QLineF.BoundedIntersection):
                    curDist = self.ptDist(intersectionPt, pt)
                    if (curDist < dist):
                        closest = (i, j)
                        dist = curDist

        # Close enough?
        if (dist <= distTh):
            return closest

        # If we didnt return yet, we didn't find anything
        return (-1, -1)

    # Get the first polygon index and the point/edge index within the given polygons that is close to the given point
    # Return (-1, -1, -1) if none is close enough
    # Return (k, i, i) if the polygon with k and the point with index i is closed
    # Return (k, i, i+1) if the edge from points i to i+1 of the kth polygon is closest
    def getClosestPointFromPolygons(self, polygons, pt):
        for idx, poly in enumerate(polygons):
            closestPt = self.getClosestPoint(poly, pt)
            if (closestPt != (-1, -1)):
                return (idx, closestPt[0], closestPt[1])
        # If we didn't return yet, we didn't find anything
        return (-1, -1, -1)

    # Check polygon close condition
    def checkClose(self):
        if (len(self.drawPoly) < 4):
            return False
        canClose = self.checkPolygonValidation(self.drawPoly)
        return canClose

    # Check if two lines intersect with each other
    def checkLineIntersect(self, line1, line2):
        intersectionPt = QtCore.QPointF()
        intersectionType = line1.intersect(line2, intersectionPt)
        # The two lines intersect with each other within the start and end points of each line
        if (intersectionType == QtCore.QLineF.BoundedIntersection):
            return True

        # Otherwise
        return False
        
    # If two lines are parallel and have reverse direction, we regard as intersection
    def checkLineReverseParallel(self, line1, line2):
        intersectionPt = QtCore.QPointF()
        intersectionType = line1.intersect(line2, intersectionPt)
        # If two lines are parallel and have reverse direction, we regard as intersection
        if (intersectionType == QtCore.QLineF.NoIntersection and 
            line1.dx() * line2.dx() + line1.dy() * line2.dy() < 0):
            return True

        # Otherwise
        return False

    # Check if valid polygon
    def checkPolygonValidation(self, poly, polygonClosed = True, mousePos = None):
        # Cannot do with points less than 2 
        if (not polygonClosed and len(poly) < 2):
            return True

        # When user is drawing the polygon
        if (not polygonClosed and mousePos):
            # Get current draw line
            testLine = QtCore.QLineF(poly[-1], mousePos)
            line = QtCore.QLineF(poly[-2], poly[-1])
            if (self.checkLineReverseParallel(line, testLine)):
                return False

            for i in range(poly.size()-2):
                pt1 = poly[i]
                pt2 = poly[i+1]
                # Construct a line and do the intersection operation
                line = QtCore.QLineF(pt1, pt2)
                if (self.checkLineIntersect(line, testLine)):
                    return False

        # When user is editing the polygon
        else:
            for i in range(poly.size()-1):
                pt1 = poly[i]
                pt2 = poly[i+1]
                line1 = QtCore.QLineF(pt1, pt2)
                for j in range(i+1, poly.size()):
                    pt3 = poly[j]
                    k = j + 1
                    if (k == poly.size()):
                        k = 0
                    pt4 = poly[k]
                    line2 = QtCore.QLineF(pt3, pt4)
                    if (j == i+1 or (k == 0 and i == 0)):
                        if (self.checkLineReverseParallel(line1, line2)):
                            return False
                    elif (self.checkLineIntersect(line1, line2)):
                        return False
        # Otherwise
        return True

	# We just closed the polygon and need to deal with this situation
    def closePolygon(self):
        poly = QtGui.QPolygonF(self.drawPoly)
        self.polygons.append(poly)
        self.drawPoly = QtGui.QPolygonF()

        # Update the selected object
        if (self.selObjs):
            obj = self.annotation.objects[self.selObjs[-1]]
            obj.polygon.append([Point(p.x(), p.y()) for p in poly])

        # When edit an object, we prohibit to new an object
        if (not self.selObjs):
            for act in self.actClosedPoly:
                act.setEnabled(True)

        if (self.polygons):
            for act in self.actSelObj:
                act.setEnabled(True)

	# Add a point to the draw polygon
    def addPtToPoly(self, pt):
        self.drawPoly.append(pt)

    # Return a copy polygon form annotated object
    def getPolygon(self, obj):
        polygons = []
        for polygon in obj.polygon:
            poly = QtGui.QPolygonF()
            for pt in polygon:
                point = QtCore.QPointF(pt.x, pt.y)
                poly.append(point)
            polygons.append(poly)
        return polygons

    # Clear the drawn polygon
    def clearPolygon(self):
        # We do not clear, since the drawPoly might be a reference on an object one
        self.polygons = list()
        self.drawPoly = QtGui.QPolygonF()

        for act in self.actClosedPoly:
            act.setEnabled(False)

        for act in self.actSelObj:
            act.setEnabled(False)

    # Edit an object's polygon or clear the polygon if multiple objects are selected
    def initPolygonFromObject(self):
        # Cannot do anything without labels
        if (not self.annotation):
            return
        # Cannot do anything without any selected object
        if (not self.selObjs):
            return
        # If there are multiple objects selected, we clear the polygon
        if (len(self.selObjs) > 1):
            self.clearPolygon()
            self.update()
            return
        # The seleted object that is used for init
        obj = self.annotation.objects[self.selObjs[-1]]
        # Make a copy to the polygon
        self.polygons = self.getPolygon(obj)

        # Enable actions that need a closed polygon
        for act in self.actClosedPoly:
            act.setEnabled(False)

        # Redraw
        self.update()

    # Merge operation helper function
    def mergePolygonsHelper(self, polygons):
        unionPolygons = []
        # union two polygon each other
        while (len(polygons)):
            poly1 = polygons[0]
            del polygons[0]
            unionFlag = False
            for idx, poly2 in enumerate(polygons):
                intersection = poly1.intersected(poly2)
                if (not intersection.isEmpty()):
                    poly1 = poly1.united(poly2)
                    # Because the result polygon of united is closed
                    # We remove the last point
                    poly1.remove(-1)
                    unionFlag = True
                    del polygons[idx]
            if (not unionFlag):
                unionPolygons.append(poly1)
            else:
                polygons.append(poly1)

        return unionPolygons

    # Merge the drawn polygons if there exists intersection
    def mergePolygons(self):
        # Cannot do merge with a current drawing polygon
        if (not self.drawPoly.isEmpty()):
            return
        
        self.polygons = self.mergePolygonsHelper(self.polygons)

        if (self.selObjs):
            obj = self.annotation.objects[self.selObjs[-1]]
            polygons = self.mergePolygonsHelper(self.getPolygon(obj))
            obj.polygon = [[Point(p.x(), p.y()) for p in poly] for poly in polygons]



    # Make the object selected by mouse the real selected object
    def selectObject(self):
        # If there is no mouse selection, we are good
        if (self.mouseObj[0] < 0):
            self.deselectObject()
            return
        # Append the object to selection if it's not in there
        if (not self.mouseObj[0] in self.selObjs):
            self.selObjs.append(self.mouseObj[0])
        else:
            self.deselectObject()

        # Update polygon
        self.initPolygonFromObject()

        for act in self.actSelObj:
            act.setEnabled(True)

        self.draggedPt = (-1, -1)

    # Deselect object
    def deselectObject(self):
        # If there is no object deselect, we are good
        if (not self.selObjs):
            return
        
        # Fisrt we try to merge the edited polygon
        if (len(self.selObjs) == 1):
            self.mergePolygons()

        # Otherwise try to find the mouse obj in the list
        if (self.mouseObj[0] in self.selObjs):
            self.selObjs.remove(self.mouseObj[0])
            self.clearPolygon()
        elif (self.mouseObj[0] == -1):
            del self.selObjs[-1]
            self.clearPolygon()

        for act in self.actSelObj:
            act.setEnabled(True)
        
        self.update()

    # Deselect all objects
    def deselectAllObjects(self):
        self.selObjs = list()
        self.mouseObj = (-1, -1)
        for act in self.actSelObj:
            act.setEnabled(False)

    # Clear the current labels
    def clearAnnotation(self):
        self.annotation = None
        self.clearPolygon()
        self.clearChanges()
        self.deselectAllObjects()

    # Setting changes
    def setChanges(self):
        self.changes = True

        for act in self.actChanges:
            act.setEnabled(True)

    # Clear changes
    def clearChanges(self):
        self.changes = False

        for act in self.actChanges:
            act.setEnabled(False)

    # Load an image 
    def loadImage(self, filename):
        success = True
        self.deselectAllObjects()
        self.clearPolygon()
        self.image = QtGui.QImage(filename)
        if (self.image.isNull()):
            success = False
        # redraw cache image
        self.redraw = True
        return success
        
    # Load the labels from json file
    def loadLabels(self, filename):
        self.clearAnnotation()

        try:
            self.annotation = Annotation()
            self.annotation.fromJsonFile(filename)
        except StandardError  as e:
            message = "Error parsing labels in {0}".format(filename)
            self.showMessage.emit(message)
        self.updateMouseObject()
        if (self.curDrawType == AnnObjectType.OCCLUSION_BOUNDARY and 
            self.annotation and self.annotation.objects and
            not self.annotation.boundaries):
            self.convertToBoundaries()

        # Redraw cache image
        self.redraw = True

    # Save labels
    def saveLabels(self, filename):
        # Status
        saved = False
        # Message to show at the status bar when done
        message = "" 
        if (self.changes and self.annotation and
            self.annotation.objects and not self.image.isNull()):
            if (self.annotation.boundaries):
                dlgTitle = "Save label"
                text = "Instance labels have been changed, do you continue to save the labels?" \
                       " Please ensure that the occlusion boundary labels synchronization."
                buttons = QtGui.QMessageBox.Yes | QtGui.QMessageBox.No
                ret = QtGui.QMessageBox.question(self, dlgTitle, text, buttons, QtGui.QMessageBox.No)
                if (ret == QtGui.QMessageBox.No):
                    return saved

            # set image dimensions
            self.annotation.imgWidth = self.image.width()
            self.annotation.imgHeight = self.image.height()

            # save to json file
            try:
                self.annotation.toJsonFile(filename)
                saved = True
                message += "Saved labels to {0}".format(filename)
            except IOError as e:
                message += "Error writting labels to {0}. Message: {1}".format(filename, e.strerror)
            if (saved):
                self.clearChanges()
        else:
            message += "Nothing to save"
            saved = True

        self.showMessage.emit(message)
        return saved

    # Object polygons convert to boundary list
    def convertToBoundaries(self):
        if (self.image.isNull()):
            return
        if (not self.annotation or not self.annotation.objects):
            return

        height = self.image.rect().height()
        width = self.image.rect().width()
        if (self.convertThread and self.convertThread.isRunning()):
            self.convertThread.quit()
            self.convertThread.wait()
        self.convertThread = QtCore.QThread()
        self.worker = ConvertToBoundariesWorker(self.annotation.objects, height, width)
        self.worker.finishedSignal.connect( 
            self.boundariesConversionCompleted)
        self.worker.moveToThread(self.convertThread)
        self.convertThread.started.connect(self.worker.convertToBoundaries)
        self.busyWaiting.emit(True)
        self.convertThread.start()
        
    # Boundaries conversion Callback function
    def boundariesConversionCompleted(self, polygon):
        # New a AnnBoundary 
        boundaries = AnnBoundary()
        boundaries.polygon = polygon
        boundaries.deleted = 0
        boundaries.verified = 0
        boundaries.user = getpass.getuser()
        boundaries.updateDate()
        self.annotation.boundaries = boundaries
        
        self.setChanges()
        
        # quit the thread
        self.convertThread.quit()
        self.convertThread.wait()
        # Hide the busy waiting overlay
        self.busyWaiting.emit(False)

        self.redraw = True

    # Create a new object from the current polygons
    def newObject(self):
        if (len(self.selObjs) > 0):
            return
        # Default label
        label = self.curLabel

        if (label):
            # Fisrt try to merge the polygons
            self.mergePolygons()
            # Append and create the new object
            self.appendObject(label, self.polygons)

        # Redraw labels
        self.redraw = True

        # Redraw
        self.update()

    # Create new object
    def appendObject(self, label, polygon):
        # Create empty annatation object if first object
        if (not self.annotation):
            self.annotation = Annotation()

        # Search the highest ID
        newID = 0
        for obj in self.annotation.objects:
            if (obj.id >= newID):
                newID = obj.id + 1

        # New object
        obj = AnnInstance()
        obj.label = label
        obj.polygon = [[Point(p.x(), p.y()) for p in poly] for poly in polygon]
        obj.id = newID
        obj.deleted = 0
        obj.verified = 0
        obj.user = getpass.getuser()
        obj.updateDate()
        obj.color = ((np.random.random((1, 3)))*255).astype(np.int32).tolist()[0]
        self.annotation.objects.append(obj)

        # Clear the drawn polygon
        self.clearPolygon()

        # setting change flag
        self.setChanges()

        # Select the new object
        self.mouseObj = (-1, -1)
        self.selectObject()

    # Delete the selected objects
    def deleteObject(self):
        # If there exists drawing polygons
        if (self.polygons):
            self.clearPolygon()

        for act in self.actSelObj:
            act.setEnabled(False)

        # Do nothing if no selected objects
        if (not self.selObjs):
            return

        # Delete from annotation
        for idx in sorted(self.selObjs, reverse=True):
            del self.annotation.objects[idx]

        self.deselectAllObjects()

        # setting change flag
        self.setChanges()
        

    # Modify the label of a selected object
    def modifyLabel(self):
        # cannot do anything without labels
        if (not self.annotation):
            return

        # cannot do anything without a single selected object
        if (len(self.selObjs) != 1):
            return

        obj = self.annotation.objects[self.selObjs[-1]]
        oldLabel = obj.label
        newLabel = self.curLabel
        self.annotation.objects[self.selObjs[-1]].label = self.curLabel

        self.showMessage.emit('Change object {0} label {1} to {2}'.format(obj.id, oldLabel, newLabel)) 

        self.setChanges()
        self.update()

    # Modify the layer level of the selected object
    def modifyLayer(self, offset):
        # cannot do anything without labels
        if (not self.annotation):
            return

        # cannot do anything without a single selected object
        if (len(self.selObjs) != 1):
            return

        # The selected object that is modified
        obj = self.annotation.objects[self.selObjs[-1]]
        # The index in the label list we are right now
        oldidx = self.selObjs[-1]
        # The index we want to move to
        newidx = oldidx + offset

        # Make sure not exceed zero and the list lenght
        newidx = min(max(newidx, 0), len(self.annotation.objects) - 1)

        # If new and old idx are equal, there is nothing to do
        if (oldidx == newidx):
            return

        # Move the entry in the labels list
        self.annotation.objects[newidx], self.annotation.objects[oldidx] = \
            self.annotation.objects[oldidx], self.annotation.objects[newidx]

        # Update the selected object to the new index
        self.selObjs[-1] = newidx
        
        self.showMessage.emit('Move object {0} with label {1} to layer {2}'.format(obj.id, obj.label, newidx))

        self.setChanges()

    # Move a object layer up
    def layerUp(self):
        self.modifyLayer(+1)
        self.update()

    # Move a object layer down
    def layerDown(self):
        self.modifyLayer(-1)
        self.update()

	# Increase label transparency
    def minus(self):
        self.transp = max(self.transp - 0.1, 0.0)
        # Redraw labels
        self.redraw = True
        self.update()

    # Decrease label transparency
    def plus(self):
        self.transp = min(self.transp + 0.1, 1.0)
        # Redraw labels
        self.redraw = True
        self.update()


    # Zoom out
    def zoomOut(self):
        self.zoomFactor -= 0.5
        self.zoomFactor = max(self.zoomFactor, 0.1)
        self.zoomFactor = min(self.zoomFactor, 10)
        self.adjustSize()
        self.update()

    # Zoom in
    def zoomIn(self):
        self.zoomFactor += 0.5
        self.zoomFactor = max(self.zoomFactor, 0.1)
        self.zoomFactor = min(self.zoomFactor, 10)
        self.adjustSize()
        self.update()

    # set label name
    def setCurrentLabelName(self, labelName):
        self.curLabel = labelName

    # set draw type
    def setCurrentDrawType(self, drawType):
        # Fisrt, we try to deselect object
        self.clearPolygon()
        self.deselectObject()
        self.deselectAllObjects()
        self.curDrawType = drawType
        if (self.curDrawType == AnnObjectType.OCCLUSION_BOUNDARY):
            if (self.changes):
                dlgTitle = "Convert?"
                text = "Do you want to convert occlusion boundary from changed instance annotations?"
                buttons = QtGui.QMessageBox.Yes | QtGui.QMessageBox.No
                ret = QtGui.QMessageBox.question(self, dlgTitle, text, buttons, QtGui.QMessageBox.Yes)
                if (ret == QtGui.QMessageBox.Yes):
                    self.convertToBoundaries()
            elif (self.annotation and not self.annotation.boundaries):
                self.convertToBoundaries()
                self.setChanges()

        # redraw labels
        self.redraw = True
        self.update()
