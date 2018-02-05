from Qt import QtCore, QtGui, QtWidgets
from Qt import __binding__ as qt_binding
PYSIDE2 = True if qt_binding in ("PySide2", "PyQt5") else False
if PYSIDE2:
    from shiboken2 import wrapInstance
    import pyside2uic
else:
    from shiboken import wrapInstance
    import pysideuic

import maya.OpenMaya as om
import maya.OpenMayaUI as omui
from maya.OpenMayaUI import MQtUtil
import maya.cmds as cmds
import maya.mel as mel
import pymel.core as pm

from collections import deque

'''
	Things to consider:
	- Each face may have a different UV set
		- Select desired UV set on mesh before using the tool
	- What if the mesh has no UV set
	- What if the UV set has no tex-coords
	- If the next face selection is not connected the sequence must start again
'''


# TODO: Initial face selected is start point
# TODO: Debug crash when polymove and sew inside context
# Deleting context works in the maya script editor
# Could the crash have something to do with the change in underlying UV data??

class Super_Stitcher(QtWidgets.QDialog):
    ctx = 'myCtx'
    def __init__(self, parent):
        self.parent = parent
        QtWidgets.QDialog.__init__(self, self.parent)

        self.setFixedHeight(100)
        self.setFixedWidth(200)

        self.btnStart = QtWidgets.QPushButton('Start Stitching')
        self.btnStart.clicked.connect(self.startTool)
        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.btnStart)
        self.setLayout(layout)


    def startTool(self):
        # mel.eval('doMenuComponentSelection("pCube1", "facet");')
        # Setup initial variables
        self.selectedMesh = None
        self.selectedTransform = None
        self.fnMesh = None
        self.fnPolys = None
        self.uvSets = []
        self.fDeq = deque([], 2)
        self.fidDeq = deque([], 2)
        self.sewEdge = False


        self.setupInitialData()
        self.setupContext()


    def closeEvent(self, event):
        self.deleteLater()
        self.deleteContext()
        cmds.setToolTo('selectSuperContext')
        event.accept()


    def deleteContext(self):
        """
        Delete the context
        :return:
        """
        if cmds.draggerContext(self.ctx, exists=True):
            print 'Deleting Context', self.ctx
            cmds.deleteUI(self.ctx)


    def setupContext(self):
        """
        Sets up our dragger context for the user to drag around with
        :return:
        """
        self.deleteContext()
        cmds.draggerContext(self.ctx, dragCommand=self.onDrag, name=self.ctx, cursor='crossHair')
        cmds.setToolTo(self.ctx)


    def setupInitialData(self):
        """ Setting up our initial data set for our selected mesh """
        self.selectedTransform = cmds.ls(sl=True)[0]
        self.selectedMesh = cmds.listRelatives(self.selectedTransform, s=True)[0]
        selectionList = om.MSelectionList()
        selectionList.add(self.selectedMesh)
        self.dagPath = om.MDagPath()
        selectionList.getDagPath(0, self.dagPath)
        self.setApiValues()


    def setApiValues(self):
        self.fnMesh = om.MFnMesh(self.dagPath)
        self.fnVerts = om.MItMeshVertex(self.dagPath)
        self.fnPolys = om.MItMeshPolygon(self.dagPath)
        self.fnMesh.getUVSetNames(self.uvSets)
        self.indexUtilPtr = om.MScriptUtil().asIntPtr()


    def getIntersection(self):
        # Create mpoint variables
        pos = om.MPoint()   # 3D point with double-precision coordinates
        dir = om.MVector()  # 3D vector with double-precision coordinates
        vpX, vpY, _ = cmds.draggerContext(self.ctx, query=True, dragPoint=True)
        # This takes vpX and vpY as input and outputs position and direction
        # values for the active view.
        # - M3dView: provides methods for working with 3D model views
        # - active3dView(): Returns the active view in the form of a class
        # - viewToWorld: Takes a point in port coordinates and
        #                returns a corresponding ray in world coordinates
        omui.M3dView().active3dView().viewToWorld(int(vpX), int(vpY), pos, dir)

        #pos2 = om.MFloatPoint(pos.x, pos.y, pos.z) # Creating a 3 vector float point to use
        #raySource = om.MFloatPoint(pos2)
        raySource = om.MFloatPoint(pos)
        rayDirection = om.MFloatVector(dir)
        faceIds = None
        triIds = None
        idsSorted = False
        maxParamPtr = 99999999
        testBothDirections = False
        accelParams = None
        hitpoint = om.MFloatPoint()
        hitRayParam = None
        hitFacePtr = om.MScriptUtil().asIntPtr()
        hitTriangle = None
        hitBary1 = None
        hitBary2 = None

        intersection = self.fnMesh.closestIntersection(raySource,
                                                       rayDirection,
                                                       faceIds,
                                                       triIds,
                                                       idsSorted,
                                                       om.MSpace.kWorld,
                                                       maxParamPtr,
                                                       testBothDirections,
                                                       accelParams,
                                                       hitpoint,
                                                       hitRayParam,
                                                       hitFacePtr,
                                                       hitTriangle,
                                                       hitBary1,
                                                       hitBary2)
        return intersection, hitFacePtr

    def onDrag(self):
        intersection, hitFacePtr = self.getIntersection()

        if intersection:
            fId = om.MScriptUtil.getInt(hitFacePtr)
            if not len(self.fidDeq):
                self.fidDeq.append(fId)
            else:
                index = self.appendDeq(inputDeq=self.fidDeq, index=len(self.fidDeq) - 1, inputVal=fId)
                if not index:
                    return

            # cmds.select('%s.f[%d]' % (self.selectedMesh, fId))
            self.fnPolys.setIndex(fId, self.indexUtilPtr)
            edgeList = om.MIntArray()
            self.fnPolys.getEdges(edgeList)

            if not len(self.fDeq):
                self.fDeq.append(edgeList)
                print 'initial fdeq', self.fDeq
                return
            else:
                #print self.fDeq
                returnCode = self.appendDeq(inputDeq=self.fDeq, index=len(self.fDeq) - 1, inputVal=edgeList, edge=True)
                if not returnCode:
                    print 'Did not append edge deq'
                    return

            prev = list(self.fDeq[0])
            curr = list(self.fDeq[1])
            matchingEdge = list(set(curr).intersection(prev))
            if matchingEdge:
                if self.sewEdge:
                    matchingEdge = matchingEdge[0]

                    # TODO: This is where we have our crash. Must figure out whats going on...
                    cmds.select('%s.e[%d]' % (self.selectedTransform, matchingEdge), replace=True)
                    #cmds.refresh()

                    # Deleting the context to test single sew function
                    print 'SEWING BRA'
                    #cmds.polyMapSewMove()
                    cmds.refresh()
                    #self.setApiValues()
                    #self.setupContext()
                    #cmds.refresh()
                    #self.sewEdge = False


    def appendDeq(self, inputDeq=None, index=0, inputVal=None, edge=False):
        #if edge:
        #    print inputDeq[index], inputVal
        if inputDeq[index] != inputVal:
            inputDeq.append(inputVal)
            if edge:
                self.sewEdge = True
            return 1
        return 0


def wrap_instance(pointer, base_type=None):
    """
    Wraps a pointer in the appropriate qt instance type
    :param pointer:
    :param base_type:
    :return: QtCore.Object
    """
    if not pointer:
        return None

    wrapper = None
    meta_object = wrapInstance(long(pointer), QtCore.QObject).metaObject()

    # determine the wrapper type
    class_name = meta_object.className()
    if hasattr(QtGui, class_name):
        wrapper = getattr(QtGui, class_name)

    if PYSIDE2:
        class_name = meta_object.className()
        if hasattr(QtWidgets, class_name):
            wrapper = getattr(QtWidgets, class_name)

    super_class_name = meta_object.superClass().className()
    if hasattr(QtCore, super_class_name):
        wrapper = getattr(QtCore, super_class_name)

    wrapper = base_type if not wrapper else wrapper

    return wrapInstance(long(pointer), wrapper)


def get_maya_main_window():
    """
    :return: QMainWindow
    """
    # noinspection PyArgumentList
    pointer = MQtUtil.mainWindow()
    if not pointer:
        raise RuntimeError('get_maya_main_window(): QMainWindow not found.')

    window = wrap_instance(pointer, QtWidgets.QMainWindow)
    assert isinstance(window, QtWidgets.QMainWindow)

    return window


def main():
    winName = 'SUPER_STITCHER'
    global myWindow
    if pm.windows.window(winName, exists=True):
        myWindow.close()
    myWindow = Super_Stitcher(parent=get_maya_main_window())
    myWindow.setObjectName(winName)
    myWindow.show()

if __name__ == '__main__':
    main()

    # cmds.polyMapSewMove()
    # cmds.polyMapSew()
    # polyMapSewMove -nf 10 -lps 0 -ch 1 pCube1.e[31];
    # mel.eval('polyMapSewMove -nf 10 -lps 0 -ch 1 %s.e[%s];'%(self.selectedMesh, matchingEdge))
    # cmds.polyMapSewMove('%s.e[%d]' % (self.selectedTransform, matchingEdge), uvs='map1', ch=1)