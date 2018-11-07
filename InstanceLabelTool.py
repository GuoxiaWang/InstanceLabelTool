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
import sys
import os
import json

from lib.waitindicator import WaitOverlay
from lib.annotation import AnnObjectType
from lib.canvas import Canvas
from lib.worker import BatchConvertToBoundariesWorker

class InstanceLabelTool(QtGui.QMainWindow):
    def __init__(self):
        super(InstanceLabelTool, self).__init__()

        # Filenames of all iamges
        self.imageList = None
        # Image directory
        self.imageDir = None
        # Current image id
        self.idx = 0

        # Ground truth extension after labeling occlusion orientation
        self.gtExt = '.polygons.json'

        # Current image as QImage
        self.image = QtGui.QImage()
        self.initUI()

    def initUI(self):
        self.canvas = Canvas(parent=self)
        self.canvas.scrollRequest.connect(self.scrollRequest)

        scroll = QtGui.QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(True)
        scroll.verticalScrollBar().setSingleStep(1)
        scroll.horizontalScrollBar().setSingleStep(1)
        self.scrollBars = {
            QtCore.Qt.Vertical: scroll.verticalScrollBar(),
            QtCore.Qt.Horizontal: scroll.horizontalScrollBar()
        }
        self.scrollArea = scroll
        self.setCentralWidget(scroll)

        self.canvas.showMessage.connect(self.statusBarShowMessage)

        self.canvas.busyWaiting.connect(self.showWaitOverlay)

        # Menu setting
        self.menuBar().setNativeMenuBar(False)

        # Add File menu
        self.fileMenuBar = self.menuBar().addMenu('&File')

        openAction = QtGui.QAction('&Open', self)
        openAction.triggered.connect(self.loadImageJsonList)
        self.fileMenuBar.addAction(openAction)

        # Add quit action to File menu
        exitAction = QtGui.QAction('&Quit', self)
        exitAction.triggered.connect(QtGui.qApp.quit)
        self.fileMenuBar.addAction(exitAction)

        # Add Tools menu
        self.toolsMenuBar = self.menuBar().addMenu('&Tools')
        
        convertToBoundariesAction = QtGui.QAction('&Batch convert to occlusion boundaries', self)
        convertToBoundariesAction.triggered.connect(self.batchConvertToOcclusionBoundaries)
        self.toolsMenuBar.addAction(convertToBoundariesAction)

        # Create a toolbar
        self.toolbar = self.addToolBar('Tools')
        
        # Add the tool buttons
        iconDir = os.path.join(os.path.dirname(__file__), 'icons')

        # Load image and label list, then show the first image and label
        loadAction = QtGui.QAction(QtGui.QIcon(os.path.join(iconDir, 'open.png')), '&Tools', self)
        loadAction.setShortcuts(['o'])
        self.setTip(loadAction, 'Open json list')
        loadAction.triggered.connect(self.loadImageJsonList)
        self.toolbar.addAction(loadAction)

        # Save the labels to json file
        saveChangesAction = QtGui.QAction(QtGui.QIcon(os.path.join(iconDir, 'save.png')), '&Tools', self)
        saveChangesAction.setShortcuts([QtGui.QKeySequence.Save])
        self.setTip(saveChangesAction, 'Save changes')
        saveChangesAction.triggered.connect(self.saveLabels)
        self.toolbar.addAction(saveChangesAction)
        saveChangesAction.setEnabled(False)
        self.canvas.actChanges.append(saveChangesAction)
        
        self.toolbar.addSeparator()

        # Load next image
        self.prevAction = QtGui.QAction(QtGui.QIcon(os.path.join(iconDir, 'prev.png')), '&Tools', self)
        self.prevAction.setShortcuts([QtGui.QKeySequence.MoveToPreviousChar])
        self.setTip(self.prevAction, 'Previous image')
        self.prevAction.triggered.connect(self.prevImage)
        self.toolbar.addAction(self.prevAction)
        self.prevAction.setEnabled(False)
        
        # Add QLabel to show current image id of all image
        self.numLabel = QtGui.QLabel()
        self.numLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.toolbar.addWidget(self.numLabel)
        
        # Load next image
        self.nextAction = QtGui.QAction(QtGui.QIcon(os.path.join(iconDir, 'next.png')), '&Tools', self)
        self.nextAction.setShortcuts([QtGui.QKeySequence.MoveToNextChar])
        self.setTip(self.nextAction, 'Next image')
        self.nextAction.triggered.connect(self.nextImage)
        self.toolbar.addAction(self.nextAction)
        self.nextAction.setEnabled(False)

        self.toolbar.addSeparator()

        # Create new object from drawn polygon
        newObjAction = QtGui.QAction(QtGui.QIcon(os.path.join(iconDir, 'newobject.png')), '&Tools', self)
        newObjAction.setShortcuts(['e'])
        self.setTip(newObjAction, 'New object')
        newObjAction.triggered.connect(self.canvas.newObject)
        self.toolbar.addAction(newObjAction)
        newObjAction.setEnabled(False)
        self.canvas.actClosedPoly.append(newObjAction)

        # Delete the selected objects
        deleteObjAction = QtGui.QAction(QtGui.QIcon(os.path.join(iconDir, 'deleteobject.png')), '&Tools', self)
        deleteObjAction.setShortcuts(['c'])
        self.setTip(deleteObjAction, 'Delete object')
        deleteObjAction.triggered.connect(self.canvas.deleteObject)
        self.toolbar.addAction(deleteObjAction)
        deleteObjAction.setEnabled(False)
        self.canvas.actSelObj.append(deleteObjAction)

        # Layer up the selected object
        layerupObjAction = QtGui.QAction(QtGui.QIcon(os.path.join(iconDir, 'layerup.png')), '&Tools', self)
        layerupObjAction.setShortcuts([QtGui.QKeySequence.MoveToPreviousLine])
        self.setTip(layerupObjAction, 'Layer up')
        layerupObjAction.triggered.connect(self.canvas.layerUp)
        self.toolbar.addAction(layerupObjAction)

        # Layer down the selected object
        layerdownObjAction = QtGui.QAction(QtGui.QIcon(os.path.join(iconDir, 'layerdown.png')), '&Tools', self)
        layerdownObjAction.setShortcuts([QtGui.QKeySequence.MoveToNextLine])
        self.setTip(layerdownObjAction, 'Layer down')
        layerdownObjAction.triggered.connect(self.canvas.layerDown)
        self.toolbar.addAction(layerdownObjAction)

        # Modify the selected object label name
        modifyLabelAction = QtGui.QAction(QtGui.QIcon(os.path.join(iconDir, 'modify.png')), '&Tools', self)
        self.setTip(modifyLabelAction, 'Modify label name')
        modifyLabelAction.triggered.connect(self.canvas.modifyLabel)
        self.toolbar.addAction(modifyLabelAction)

        self.toolbar.addSeparator()
        
        # Zoom out
        zoomOutAction = QtGui.QAction(QtGui.QIcon(os.path.join(iconDir, 'zoomout.png')), '&Tools', self)
        self.setTip(zoomOutAction, 'Mouse wheel to scroll down')
        zoomOutAction.triggered.connect(self.canvas.zoomOut)
        self.toolbar.addAction(zoomOutAction)
        
        # Zoom in
        zoomInAction = QtGui.QAction(QtGui.QIcon(os.path.join(iconDir, 'zoomin.png')), '&Tools', self)
        self.setTip(zoomInAction, 'Mouse wheel to scroll up')
        zoomInAction.triggered.connect(self.canvas.zoomIn)
        self.toolbar.addAction(zoomInAction)
        
		# Decrease transparency
        minusAction = QtGui.QAction(QtGui.QIcon(os.path.join(iconDir, 'minus.png')), '&Tools', self)
        minusAction.setShortcuts(['-'])
        self.setTip(minusAction, 'Decrease transparency')
        minusAction.triggered.connect(self.canvas.minus)
        self.toolbar.addAction(minusAction)
        
        # Plus transparency
        plusAction = QtGui.QAction(QtGui.QIcon(os.path.join(iconDir, 'plus.png')), '&Tools', self)
        plusAction.setShortcuts(['+'])
        self.setTip(plusAction, 'Increase transparency')
        plusAction.triggered.connect(self.canvas.plus)
        self.toolbar.addAction(plusAction)

        self.toolbar.addSeparator()

		# Draw type sets
        self.drawTypeSetComboBox = QtGui.QComboBox()
        self.loadDrawTypeSet()
        self.drawTypeSetComboBox.currentIndexChanged.connect(self.drawTypeChange)
        self.toolbar.addWidget(self.drawTypeSetComboBox)

		# Label name sets
        self.labelSetComboBox = QtGui.QComboBox()
        self.loadLabelCategoriesFromFile()
        self.labelSetComboBox.currentIndexChanged.connect(self.labelChange)
        self.toolbar.addWidget(self.labelSetComboBox)

        # Set a wait overlay
        self.waitOverlay = WaitOverlay(self)
        self.waitOverlay.hide()

        # The default text for the status bar
        self.defaultStatusbar = 'Ready'
        # Create a statusbar and init with default
        self.statusBar().showMessage(self.defaultStatusbar)

        # Enable mouse move events
        self.setMouseTracking(True)
        self.toolbar.setMouseTracking(True)

        # Open in full screen
        screenShape = QtGui.QDesktopWidget().screenGeometry()
        self.resize(screenShape.width(), screenShape.height())

        # Set the title
        self.applicationTitle = 'Instance Label Tool v1.0'
        self.setWindowTitle(self.applicationTitle)

        # Show the application
        self.show()

    def setTip(self, action, tip):
        shortcuts = "', '".join([str(s.toString()) for s in action.shortcuts()])
        if (not shortcuts):
            shortcuts = 'none'
        tip += " (Hotkeys: '" + shortcuts + "')"
        action.setStatusTip(tip)
        action.setToolTip(tip)

    # show message through statusbar
    def statusBarShowMessage(self, message):
        self.statusBar().showMessage(message)

    def resizeEvent(self, event):    
        self.waitOverlay.resize(event.size())
        event.accept()

    @QtCore.pyqtSlot(bool)
    def showWaitOverlay(self, show=True):
        if (show):
            self.waitOverlay.show()
        else:
            self.waitOverlay.hide()

    # Load image json list
    def loadImageJsonList(self):
        fname = QtGui.QFileDialog.getOpenFileName(self, 'Open image list .json file', '.', 'Json file (*.json)')
        fname = str(fname)
        if (os.path.isfile(fname)):
            self.imageDir = os.path.split(fname)[0]
            with open(fname, 'r') as f:
                jsonText = f.read()
                self.imageList = json.loads(jsonText)
                if (not isinstance(self.imageList, list)):
                    self.statusBarShowMessage("Invalid image list, please check json format")
                    return
                if (self.imageList):
                    self.idx = 0
                self.updatePrevNextToolbarStatus()
                self.loadImage()
                self.update()

    # Load the currently selected image
    def loadImage(self):
        success = False
        message = self.defaultStatusbar
        if self.imageList:
            filename = self.imageList[self.idx]
            filename = os.path.join(self.imageDir, filename)
            self.numLabel.setText('{0}/{1}'.format(self.idx+1, len(self.imageList)))
            success = self.canvas.loadImage(filename)
            if (not success):
                message = "failed to read image: {0}".format(filename)
            else:
                message = filename
            self.loadLabels()
            self.canvas.update()
        else:
            self.numLabel.setText('')
        self.statusBarShowMessage(message)

    # Get the filename where to load/save labels
    # Returns empty string  if not possible
    def getLabelFilename(self):
        filename = ""
        if (self.imageList):
            filename = self.imageList[self.idx]
            filename = os.path.join(self.imageDir, filename)
            imageExt = os.path.splitext(filename)[1]
            filename = filename.replace(imageExt, self.gtExt)
            filename = os.path.normpath(filename)
        return filename

    # Load the labels from json file
    def loadLabels(self):
        filename = self.getLabelFilename()
        if (not filename or not os.path.isfile(filename)):
            self.canvas.clearAnnotation()
            return
        self.canvas.loadLabels(filename)

    # Save the labels to json file
    def saveLabels(self):
        filename = self.getLabelFilename()
        if (filename):
            self.canvas.saveLabels(filename)

    # Scroll canvas
    @QtCore.pyqtSlot(int, int)
    def scrollRequest(self, offsetX, offsetY):
        hBar = self.scrollBars[QtCore.Qt.Horizontal]
        hBar.setValue(hBar.value() - offsetX)
        vBar = self.scrollBars[QtCore.Qt.Vertical]
        vBar.setValue(vBar.value() - offsetY)


    # load previous Image
    @QtCore.pyqtSlot()
    def prevImage(self):
        self.saveLabels()
        self.idx = max(self.idx - 1, 0)
        self.updatePrevNextToolbarStatus()
        self.loadImage()

    # Load next Image
    @QtCore.pyqtSlot()
    def nextImage(self):
        self.saveLabels()
        self.idx = min(self.idx + 1, len(self.imageList)-1)
        self.updatePrevNextToolbarStatus()
        self.loadImage()

    # Initialize prev and next toolbar status
    def updatePrevNextToolbarStatus(self):
        if (len(self.imageList) > 0 and self.idx < len(self.imageList) - 1):
            self.nextAction.setEnabled(True)
        else:
            self.nextAction.setEnabled(False)
        if (self.idx <= 0):
            self.prevAction.setEnabled(False)
        else:
            self.prevAction.setEnabled(True)

    # Load catogories label from config file
    def loadLabelCategoriesFromFile(self):
        filename = os.path.join(os.path.dirname(__file__), 'config.json')
        try:
            with open(filename, 'r') as f:
                jsonText = f.read()
                jsonDict = json.loads(jsonText)
                categories = [c['name'] for c in jsonDict['categories']]
                self.labelSetComboBox.addItems(categories)
                self.canvas.setCurrentLabelName(categories[0])
        except StandardError as e:
            msgBox = QtGui.QMessageBox(self)
            msgBox.setWindowTitle("Error")
            msgBox.setText("Plase check config.json file!")
            msgBox.setIcon(QtGui.QMessageBox.Critical)
            msgBox.setStandardButtons(QtGui.QMessageBox.Abort)
            msgBox.exec_()
            sys.exit()

    # label selection changed, we update the current label name 
    def labelChange(self, index):
        labelName = self.labelSetComboBox.currentText()
        self.canvas.setCurrentLabelName(str(labelName))

    # Load draw type set
    def loadDrawTypeSet(self):
        # See DrawType for more information
        drawTypeName = ['instance', 'boundary']
        self.drawTypeSetComboBox.addItems(drawTypeName)
        self.canvas.setCurrentDrawType(AnnObjectType.INSTANCE)

    # Draw type changed, we update the current draw type
    def drawTypeChange(self, index):
        self.canvas.setCurrentDrawType(index)

    # Batch operation, convert to occlusion boundary 
    # from instance labels automatically
    def batchConvertToOcclusionBoundaries(self):
        dlgTitle = "Batch convert to occlusion boundary"
        # Check if load image list
        if (not self.imageList):
            text = "Need load image list firstly."
            buttons = QtGui.QMessageBox.Yes
            ret = QtGui.QMessageBox.information(self, dlgTitle, text, buttons, QtGui.QMessageBox.Yes)
            return 
        
        self.progressDialog = QtGui.QProgressDialog("Converting ...", "Cancel", 0, len(self.imageList), self)
        self.progressDialog.setWindowTitle(dlgTitle)
        self.progressDialog.resize(350, self.progressDialog.height())
        self.progressDialog.setWindowModality(QtCore.Qt.WindowModal)
        self.progressDialog.canceled.connect(self.batchConvertStop)

        self.batchConvertThread = QtCore.QThread()
        self.batchConvertWorker = BatchConvertToBoundariesWorker(self.imageList, self.imageDir, self.gtExt)
        self.batchConvertWorker.information.connect(self.dealwithBatchConvertUserOperation)
        self.batchConvertWorker.updateProgress.connect(self.updateBatchConvertProgressDialog)
        self.batchConvertWorker.finished.connect(self.batchConvertStop)
        self.batchConvertWorker.moveToThread(self.batchConvertThread)
        self.batchConvertThread.started.connect(self.batchConvertWorker.batchConvertToBoundaries)
        self.batchConvertThread.start()
        
        self.progressDialog.exec_()

    @QtCore.pyqtSlot(int, str)
    def updateBatchConvertProgressDialog(self, value, labelText):
        self.progressDialog.setValue(value)
        self.progressDialog.setLabelText(labelText)

    @QtCore.pyqtSlot()
    def batchConvertStop(self):
        self.batchConvertWorker.stop()
        self.batchConvertThread.quit()
        self.batchConvertThread.wait()
        self.progressDialog.close()

    @QtCore.pyqtSlot(str, str)
    def dealwithBatchConvertUserOperation(self, infoType, message):
        dlgTitle = "Batch convert to occlusion boundary"
        buttons = None
        defaultButtons = None
        if (infoType == "IOError"):
            buttons = QtGui.QMessageBox.Yes | QtGui.QMessageBox.No
            defaultButtons = QtGui.QMessageBox.Yes
        elif (infoType == "Overwrite"):
            buttons = QtGui.QMessageBox.Yes | QtGui.QMessageBox.YesToAll | QtGui.QMessageBox.No
            defaultButtons = QtGui.QMessageBox.Yes
        self.batchConvertWorker.userOperationResult = QtGui.QMessageBox.information(
            self, dlgTitle, message, buttons, defaultButtons)
        self.batchConvertWorker.waitCondition.wakeAll()

def main():
    
    app = QtGui.QApplication(sys.argv)
    tool = InstanceLabelTool()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
