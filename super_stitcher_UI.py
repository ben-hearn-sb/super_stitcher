import maya.OpenMaya as om
import maya.OpenMayaUI as omui
import maya.cmds as cmds
import maya.mel as mel

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

class Super_Stitcher():
	def __init__(self):
		#mel.eval('doMenuComponentSelection("pCube1", "facet");')
		self.ctx = 'myCtx'
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
		
	def deleteContext(self):
		if cmds.draggerContext(self.ctx, exists=True):
			print 'Deleting Context', self.ctx
			cmds.deleteUI(self.ctx)
		
	def setupContext(self):
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
	
	def onDrag(self):
		vpX, vpY, _ = cmds.draggerContext(self.ctx, query=True, dragPoint=True)
		pos = om.MPoint()
		dir = om.MVector()
		omui.M3dView().active3dView().viewToWorld(int(vpX), int(vpY), pos, dir)
		pos2 = om.MFloatPoint(pos.x, pos.y, pos.z)
		
		raySource = om.MFloatPoint(pos2)
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
		
		if intersection:
			setIndex = 0
			fId = om.MScriptUtil.getInt(hitFacePtr)
			if not len(self.fidDeq):
				#print 'Fucking fId', fId
				self.fidDeq.append(fId)
				setIndex = 1
			else:
				#print 'Fucking fId', fId
				setIndex = self.appendDeq(inputDeq=self.fidDeq, index=len(self.fidDeq)-1, inputVal=fId)
				if not setIndex:
					return
			#cmds.select('%s.f[%d]' % (self.selectedMesh, fId))
			self.fnPolys.setIndex(fId, self.indexUtilPtr)
			edgeList = om.MIntArray()
			self.fnPolys.getEdges(edgeList)
			
			if not len(self.fDeq):
				self.fDeq.append(edgeList)
				print 'initial fdeq', self.fDeq
				return
			else:
				print self.fDeq
				returnCode = self.appendDeq(inputDeq=self.fDeq, index=len(self.fDeq)-1, inputVal=edgeList, edge=True)
				if not returnCode:
					print 'Did not append edge deq'
					return
			prev = list(self.fDeq[0])
			curr = list(self.fDeq[1])
			matchingEdge = list(set(curr).intersection(prev))
			if matchingEdge:
				if self.sewEdge:
					matchingEdge = matchingEdge[0]
					cmds.select('%s.e[%d]' % (self.selectedTransform, matchingEdge), replace=True)
					self.deleteContext()
					#cmds.polyMapSewMove()
					self.setApiValues()
					self.setupContext()
					cmds.refresh()
					self.sewEdge = False
			
	def appendDeq(self, inputDeq=None, index=0, inputVal=None, edge=False):
		if edge:
			print inputDeq[index], inputVal
		if inputDeq[index] != inputVal:
			inputDeq.append(inputVal)
			if edge:
				self.sewEdge = True
			return 1
		return 0

def main():
	Super_Stitcher()
	
if __name__ == '__main__':
	main()
	
# cmds.polyMapSewMove()
# cmds.polyMapSew()
# polyMapSewMove -nf 10 -lps 0 -ch 1 pCube1.e[31];
# mel.eval('polyMapSewMove -nf 10 -lps 0 -ch 1 %s.e[%s];'%(self.selectedMesh, matchingEdge))
# cmds.polyMapSewMove('%s.e[%d]' % (self.selectedTransform, matchingEdge), uvs='map1', ch=1)