import re
import numpy as np
import GeometryFunctions as gf
import GeneralLattice as gl
from scipy import spatial, optimize
#from sklearn.cluster import AffinityPropagation
from skimage.morphology import skeletonize, thin, medial_axis, label, remove_small_holes

class LAMMPSData(object):
    def __init__(self,strFilename: str, intLatticeType: int):
        self.__dctTimeSteps = dict()
        lstNumberOfAtoms = []
        lstTimeSteps = []
        lstColumnNames = []
        lstBoundaryType = []
        self.__Dimensions = 3 # assume 3d unless file shows the problem is 2d
        with open(strFilename) as Dfile:
            while True:
                lstBounds = []
                try:
                    line = next(Dfile).strip()
                except StopIteration as EndOfFile:
                    break
                if "ITEM: TIMESTEP" != line:
                    raise Exception("Unexpected "+repr(line))
                timestep = int(next(Dfile).strip())
                lstTimeSteps.append(timestep)
                line = next(Dfile).strip()
                if "ITEM: NUMBER OF ATOMS" != line:
                    raise Exception("Unexpected "+repr(line))
                N = int(next(Dfile).strip())
                lstNumberOfAtoms.append(N)
                line = next(Dfile).strip()
                if "ITEM: BOX BOUNDS" != line[0:16]:
                    raise Exception("Unexpected "+repr(line))
                lstBoundaryType = line[17:].strip().split()
                lstBounds.append(list(map(float, next(Dfile).strip().split())))
                lstBounds.append(list(map(float, next(Dfile).strip().split())))
                if len(lstBoundaryType)%3 == 0:
                    lstBounds.append(list(map(float, next(Dfile).strip().split())))
                else:
                    self.__Dimensions = 2
                line = next(Dfile).strip()
                if "ITEM: ATOMS id" != line[0:14]:
                    raise Exception("Unexpected "+repr(line))
                lstColumnNames = line[11:].strip().split()
                intNumberOfColumns = len(lstColumnNames)
                objTimeStep = LAMMPSAnalysis(timestep, N,intNumberOfColumns,lstColumnNames, lstBoundaryType, lstBounds,intLatticeType)
                objTimeStep.SetColumnNames(lstColumnNames)
                for i in range(N):
                    line = next(Dfile).strip().split()
                    objTimeStep.SetRow(i,list(map(float,line)))
                objTimeStep.CategoriseAtoms()
                self.__dctTimeSteps[str(timestep)] = objTimeStep            
            self.__lstTimeSteps = lstTimeSteps
            self.__lstNumberOfAtoms = lstNumberOfAtoms
    def GetTimeSteps(self):
        return self.__lstTimeSteps
    def GetAtomNumbers(self):
        return self.__lstNumberOfAtoms
    def GetTimeStep(self, strTimeStep: str):
        return self.__dctTimeSteps[strTimeStep]
    def GetTimeStepByIndex(self, intIndex : int):
        return self.__dctTimeSteps[str(self.__lstTimeSteps[intIndex])]
    def GetNumberOfDimensions(self)-> int:
        return self.__Dimensions 
        
       
class LAMMPSTimeStep(object):
    def __init__(self,fltTimeStep: float,intNumberOfAtoms: int, lstColumnNames: list, lstBoundaryType: list, lstBounds: list):
        self.__Dimensions = 3 #assume three dimensional unless specificed otherwise
        self.__NumberOfAtoms = intNumberOfAtoms
        self.__NumberOfColumns = len(lstColumnNames)
        self.__TimeStep = fltTimeStep
        self.__AtomData = np.zeros([intNumberOfAtoms,self.__NumberOfColumns])
        self.__ColumnNames = lstColumnNames
        self.SetBoundBoxLabels(lstBoundaryType)
        self.SetBoundBoxDimensions(lstBounds)
    def SetRow(self, intRowNumber: int, lstRow: list):
        self.__AtomData[intRowNumber] = lstRow
    def GetRow(self,intRowNumber: int):
        return self.__AtomData[intRowNumber]
    def GetRows(self, lstOfRows: list):
        return self.__AtomData[lstOfRows,:]
    def GetAtomsByID(self, lstOfAtomIDs: list, intAtomColumn = 0):
        return self.__AtomData[np.isin(self.__AtomData[:,intAtomColumn],lstOfAtomIDs)]
    def GetAtomData(self):
        return self.__AtomData
    def SetColumnNames(self, lstColumnNames):
        self.__ColumnNames = lstColumnNames
    def GetColumnNames(self): 
        return self.__ColumnNames
    def GetColumnByIndex(self, intStructureIndex: int):
        return self.__AtomData[:,intStructureIndex]
    def GetColumnByName(self, strColumnName: str):
        if self.__ColumnNames != []:
            intStructureIndex = self.__ColumnNames.index(strColumnName)
            return self.GetColumnByIndex(intStructureIndex)
    def SetBoundBoxLabels(self, lstBoundBox: list):
        self.__BoundBoxLabels = lstBoundBox
        if lstBoundBox[0] == 'xy':
            self.__Cuboid = False
            self.__BoundaryTypes = lstBoundBox[self.__Dimensions:]
        else:
            self.__Cuboid = True
            self.__BoundaryTypes = lstBoundBox
    def GetBoundBoxLabels(self):
        return self.__BoundBoxLabels
    def SetBoundBoxDimensions(self, lstBoundBox):
        self.__BoundBoxDimensions = np.array(lstBoundBox)
        self.__Dimensions = len(lstBoundBox)
        arrCellVectors = np.zeros([self.__Dimensions, self.__Dimensions])
        lstOrigin = []
        for j in range(len(lstBoundBox)):
            lstOrigin.append(lstBoundBox[j][0])
            arrCellVectors[j,j] = lstBoundBox[j][1] - lstBoundBox[j][0]
        if len(lstBoundBox[0]) ==3: #then there are tiltfactors so include "xy" tilt
            arrCellVectors[1,0] = lstBoundBox[0][2]
            if self.__Dimensions == 3: #and there is also a z direction so include "xz" and "yz" tilts
                arrCellVectors[0,0] = arrCellVectors[0,0] -arrCellVectors[1,0] 
                arrCellVectors[2,0] = lstBoundBox[1][2]
                arrCellVectors[2,1] = lstBoundBox[2][2]
        self.__Origin = np.array(lstOrigin)
        self.__CellVectors  = arrCellVectors   
        self.__CellCentre = np.mean(arrCellVectors,axis=0)*self.__Dimensions/2+self.__Origin
        self.__CellBasis = np.zeros([self.__Dimensions,self.__Dimensions])
        self.__UnitCellBasis = np.zeros([self.__Dimensions,self.__Dimensions])
        for j, vctCell in enumerate(self.__CellVectors):
            self.__CellBasis[j] = vctCell 
            self.__UnitCellBasis[j] = gf.NormaliseVector(vctCell)
        self.__BasisConversion = np.linalg.inv(self.__CellBasis)
        self.__UnitBasisConversion = np.linalg.inv(self.__UnitCellBasis)
    def GetBasisConversions(self):
        return self.__BasisConversion
    def GetUnitBasisConversions(self):
        return self.__UnitBasisConversion
    def GetCellBasis(self):
        return self.__CellBasis
    def GetUnitCellBasis(self):
        return self.__UnitCellBasis
    def GetNumberOfAtoms(self):
        return self.__NumberOfAtoms
    def GetNumberOfColumns(self):
        return self.__NumberOfColumns
    def GetCellVectors(self)->np.array:
        return self.__CellVectors
    def GetOrigin(self):
        return self.__Origin
    def GetNumberOfDimensions(self)->int:
        return self.__Dimensions
    def GetCellCentre(self):
        return self.__CellCentre
    def PeriodicEquivalents(self, inPositionVector: np.array)->np.array: #For POSITION vectors only for points within   
        arrVector = np.array([inPositionVector])                         #the simulation cell
        arrCellCoordinates = np.matmul(inPositionVector, self.__BasisConversion)
        for i,strBoundary in enumerate(self.__BoundaryTypes):
            if strBoundary == 'pp':
                 if  arrCellCoordinates[i] > 0.5:
                     arrVector = np.append(arrVector, np.subtract(arrVector,self.__CellVectors[i]),axis=0)
                 elif arrCellCoordinates[i] <= 0.5:
                     arrVector = np.append(arrVector, np.add(arrVector,self.__CellVectors[i]),axis=0)                  
        return arrVector
    def MoveToSimulationCell(self, inPositionVector: np.array)->np.array:
        return gf.WrapVectorIntoSimulationCell(self.__CellBasis, self.__BasisConversion, inPositionVector)
    def PeriodicShiftCloser(self, inFixedPoint: np.array, inPointToShift: np.array)->np.array:
        arrPeriodicVectors = self.PeriodicEquivalents(inPointToShift)
        fltDistances = list(map(np.linalg.norm, np.subtract(arrPeriodicVectors, inFixedPoint)))
        return arrPeriodicVectors[np.argmin(fltDistances)]
    def StandardiseOrientationData(self):
        self.__AtomData[:, [self.GetColumnNames().index('OrientationX'),self.GetColumnNames().index('OrientationY'),self.GetColumnNames().index('OrientationZ'), self.GetColumnNames().index('OrientationW')]]=np.apply_along_axis(gf.FCCQuaternionEquivalence,1,self.GetOrientationData()) 
    def GetOrientationData(self)->np.array:
        return (self.__AtomData[:, [self.GetColumnNames().index('OrientationX'),self.GetColumnNames().index('OrientationY'),self.GetColumnNames().index('OrientationZ'), self.GetColumnNames().index('OrientationW')]])  
    def GetData(self, inDimensions: np.array, lstOfColumns):
        return np.where(self.__AtomData[:,lstOfColumns])


class LAMMPSPostProcess(LAMMPSTimeStep):
    def __init__(self, fltTimeStep: float,intNumberOfAtoms: int, intNumberOfColumns: int, lstColumnNames: list, lstBoundaryType: list, lstBounds: list,intLatticeType: int):
        LAMMPSTimeStep.__init__(self,fltTimeStep,intNumberOfAtoms, lstColumnNames, lstBoundaryType, lstBounds)
        self.__Dimensions = self.GetNumberOfDimensions()
        self._LatticeStructure = intLatticeType #lattice structure type as defined by OVITOS
        self._intStructureType = int(self.GetColumnNames().index('StructureType'))
        self._intPositionX = int(self.GetColumnNames().index('x'))
        self._intPositionY = int(self.GetColumnNames().index('y'))
        self._intPositionZ = int(self.GetColumnNames().index('z'))
        self._intPE = int(self.GetColumnNames().index('c_pe1'))
        self.CellHeight = np.linalg.norm(self.GetCellVectors()[2])
    def CategoriseAtoms(self):    
        lstOtherAtoms = list(np.where(self.GetColumnByIndex(self._intStructureType).astype('int') == 0)[0])
        lstLatticeAtoms =  list(np.where(self.GetColumnByIndex(self._intStructureType).astype('int') == self._LatticeStructure)[0])
        lstUnknownAtoms = list(np.where(np.isin(self.GetColumnByIndex(self._intStructureType).astype('int') ,[0,1],invert=True))[0])
        self.__LatticeAtoms = lstLatticeAtoms
        self.__NonLatticeAtoms = lstOtherAtoms + lstUnknownAtoms
        self.__OtherAtoms = lstOtherAtoms
        self.__NonLatticeTree =  spatial.KDTree(list(zip(*self.__PlotList(lstOtherAtoms+lstUnknownAtoms))))
        self.__LatticeTree = spatial.KDTree(list(zip(*self.__PlotList(lstLatticeAtoms))))
        self.__UnknownAtoms = lstUnknownAtoms
    def GetNonLatticeAtoms(self):
        return self.GetRows(self.__NonLatticeAtoms)
    def GetUnknownAtoms(self):
        return self.GetRows(self.__UnknownAtoms) 
    def GetLatticeAtoms(self):
        return self.GetRows(self.__LatticeAtoms)  
    def GetOtherAtoms(self):
        return self.GetRows(self.__OtherAtoms)
    def GetNumberOfNonLatticeAtoms(self):
        return len(self.__NonLatticeAtoms)
    def GetNumberOfOtherAtoms(self)->int:
        return len(self.GetRows(self.__OtherAtoms))
    def GetNumberOfLatticeAtoms(self)->int:
        return len(self.__LatticeAtoms)
    def PlotGrainAtoms(self, strGrainNumber: str):
        return self.__PlotList(self.__LatticeAtoms)
    def PlotUnknownAtoms(self):
        return self.__PlotList(self.__UnknownAtoms)
    def PlotPoints(self, inArray: np.array)->np.array:
        return inArray[:,0],inArray[:,1], inArray[:,2]
    def __PlotList(self, strList: list):
        arrPoints = self.GetRows(strList)
        return arrPoints[:,self._intPositionX], arrPoints[:,self._intPositionY], arrPoints[:,self._intPositionZ]
    def __GetCoordinate(self, intIndex: int):
        arrPoint = self.GetRow(intIndex)
        return arrPoint[self._intPositionX:self._intPositionZ+1]
    def __GetCoordinates(self, strList: list):
        arrPoints = self.GetRows(strList)
        return arrPoints[:,self._intPositionX:self._intPositionZ+1]
    def MakePeriodicDistanceMatrix(self, inVector1: np.array, inVector2: np.array)->np.array:
        arrPeriodicDistance = np.zeros([len(inVector1), len(inVector2)])
        for j in range(len(inVector1)):
            for k in range(j,len(inVector2)):
                arrPeriodicDistance[j,k] = self.PeriodicMinimumDistance(inVector1[j],inVector2[k])
        if np.shape(arrPeriodicDistance)[0] == np.shape(arrPeriodicDistance)[1]:
            return arrPeriodicDistance + arrPeriodicDistance.T - np.diag(arrPeriodicDistance.diagonal())
        else:
            return arrPeriodicDistance
    def PeriodicMinimumDistance(self, inVector1: np.array, inVector2: np.array)->float:
        arrVectorPeriodic = self.PeriodicEquivalents(np.abs(inVector1-inVector2))
        return np.min(np.linalg.norm(arrVectorPeriodic, axis=1))
    def FindNonGrainMean(self, inPoint: np.array, fltRadius: float): 
        lstPointsIndices = []
        #arrPeriodicPositions = self.PeriodicEquivalents(inPoint)
        lstPointsIndices = self.FindCylindricalAtoms(self.GetOtherAtoms()[:,0:self._intPositionZ+1],inPoint,fltRadius, self.CellHeight, True)
        #for j in arrPeriodicPositions:
        #    lstPointsIndices.extend(self.FindCylindricalAtoms(self.GetRows(self.__NonLatticeAtoms)[:,self._intPositionX:self._intPositionX+3],j,fltRadius, self.CellHeight))
        # for intIndex,arrPoint in enumerate(arrPeriodicPositions): 
        #         lstPointsIndices= self.__NonLatticeTree.query_ball_point(arrPoint, fltRadius)
        #         if len(lstPointsIndices) > 0:
        #             lstPoints.extend(np.subtract(self.__NonLatticeTree.data[lstPointsIndices],arrPeriodicTranslations[intIndex]))
        lstPointsIndices = list(np.unique(lstPointsIndices))
        #arrPoints = self.GetRows(lstPointsIndices)[:,self._intPositionX:self._intPositionZ+1]
        arrPoints = self.GetAtomsByID(lstPointsIndices)[:,self._intPositionX:self._intPositionZ+1]
        for j in range(len(arrPoints)):
            arrPoints[j] = self.PeriodicShiftCloser(inPoint, arrPoints[j])
        if len(arrPoints) ==0:
            return inPoint
        else:
           return np.mean(arrPoints, axis=0)           
    def FindCylindricalAtoms(self,arrPoints, arrCentre: np.array, fltRadius: float, fltHeight: float, blnPeriodic =True)->list: #arrPoints are [atomId, x,y,z]
        lstIndices = []
        if blnPeriodic:
            arrCentres = self.PeriodicEquivalents(arrCentre)
            for j in arrCentres:
                lstIndices.extend(gf.CylindricalVolume(arrPoints[:,1:4],j,fltRadius,fltHeight))
        else:
            lstIndices.extend(gf.CylindricalVolume(arrPoints[:,1:4],arrCentre,fltRadius,fltHeight))
        lstIndices = list(np.unique(lstIndices))
        return list(arrPoints[lstIndices,0])
    def FindBoxAtoms(self, arrPoints: np.array, arrCentre: np.array, arrLength: np.array, arrWidth: np.array,
    arrHeight: np.array, blnPeriodic = True)->list:
        lstIndices = []
        if blnPeriodic: 
            arrCentres = self.PeriodicEquivalents(arrCentre)
            for j in arrCentres:
                lstIndices.extend(gf.ParallelopipedVolume(arrPoints[:,1:4],j, arrLength, arrWidth, arrHeight))
        else:
            lstIndices.extend(gf.ParallelopipedVolume(arrPoints[:,1:4],arrCentre, arrLength, arrWidth, arrHeight))
        lstIndices = list(np.unique(lstIndices))
        return list(arrPoints[lstIndices,0])
    def FindValuesInBox(self, arrPoints: np.array, arrCentre: np.array, arrLength: np.array, arrWidth: np.array, 
    arrHeight: np.array, intColumn: int):
        lstIDs = self.FindBoxAtoms(arrPoints, arrCentre, arrLength, arrWidth,arrHeight)
        return self.GetAtomsByID(lstIDs)[:,intColumn]
    def FindValuesInCylinder(self, arrPoints: np.array ,arrCentre: np.array, fltRadius: float, fltHeight: float, intColumn: int): 
        lstIDs = self.FindCylindricalAtoms(arrPoints, arrCentre, fltRadius, fltHeight)
        #for j in lstIndices:
        #    lstRows.extend(np.where(np.linalg.norm(self.GetAtomData()[:,1:4] - arrPoints[j],axis=1)==0)[0])
        #lstRows = list(np.unique(lstRows))
        return self.GetAtomsByID(lstIDs)[:, intColumn]

class LAMMPSAnalysis(LAMMPSPostProcess):
    def __init__(self, fltTimeStep: float,intNumberOfAtoms: int, intNumberOfColumns: int, lstColumnNames: list, lstBoundaryType: list, lstBounds: list,intLatticeType: int):
        LAMMPSPostProcess.__init__(self, fltTimeStep,intNumberOfAtoms, intNumberOfColumns, lstColumnNames, lstBoundaryType, lstBounds,intLatticeType)
        self.__GrainBoundaries = []
    def EstimateTripleLineEnergy(self,fltGridSize: float, fltSearchRadius: float, fltIncrement: float):
            arrEnergy = np.zeros([len(self.__TripleLines),3])
            fltPEDatum = np.median(self.GetLatticeAtoms()[:,self._intPE])
            self.FindTriplePoints(fltGridSize, fltSearchRadius)
            #fltHeight = np.dot(self.GetCellVectors()[2], np.array([0,0,1]))
            for j in range(len(self.__TripleLines)):
                lstRadius = []
                lstExcessEnergy = [] #excess energy above the grain energy which includes a strain energy contribution
                lstTripleLineEnergy = [] #excess energy in the triple line
                fltClosest = np.sort(self.__TripleLineDistanceMatrix[j])[1] #finds the closest triple line
                for i in range(0, np.floor(fltClosest/(2*fltIncrement)).astype('int')): #only search halfway between the points
                    arrCurrentTripleLine = self.MoveToSimulationCell(self.__TripleLines[j])
                    arrCurrentTripleLine[2] = self.CellHeight/2
                    r=i*fltIncrement
                    lstRadius.append(r)
                    arrPEValues = self.FindValuesInCylinder(self.GetAtomData()[:,0:self._intPositionZ+1],arrCurrentTripleLine,r,2*self.CellHeight,self._intPE)
                    lstExcessEnergy.append(np.sum(arrPEValues)-fltPEDatum*len(arrPEValues)) #subtract off grain energy
                pLinearGB = optimize.curve_fit(gf.LinearRule,lstRadius, lstExcessEnergy)[0]
                for k in range(len(lstRadius)):
                    lstTripleLineEnergy.append(lstExcessEnergy[k]-pLinearGB[0]*lstRadius[k]) #subtract off GB energy
                pLinearTJ = optimize.curve_fit(gf.LinearRule,lstRadius, lstTripleLineEnergy)[0]    
                if np.abs(np.mean(lstTripleLineEnergy) - pLinearGB[1]) > 0.0001 or np.abs(pLinearTJ[0]) > 0.0001:
                    raise("Fitting parameters are beyond tolerance")
                arrEnergy[j,0] = fltClosest/2
                arrEnergy[j,1] = lstExcessEnergy[-1]
                arrEnergy[j,2] = pLinearTJ[1]
            return arrEnergy
    def MergePeriodicTripleLines(self, fltDistanceTolerance: float):
        lstMergedIndices = []
        setIndices = set(range(self.GetNumberOfTripleLines()))
        lstCurrentIndices = []
        arrPeriodicDistanceMatrix = self.MakePeriodicDistanceMatrix(self.__TripleLines,self.__TripleLines)
        while len(setIndices) > 0:
            lstCurrentIndices = list(*np.where(arrPeriodicDistanceMatrix[setIndices.pop()] < fltDistanceTolerance))
            lstMergedIndices.append(lstCurrentIndices)
            setIndices = setIndices.difference(lstCurrentIndices)
        return lstMergedIndices
    def FindTriplePoints(self,fltGridLength: float, fltSearchRadius: float):
        lstGrainBoundaries = []
        lstGrainBoundaryObjects = []
        fltMidHeight = self.CellHeight/2
        objQPoints = QuantisedRectangularPoints(self.GetOtherAtoms()[:,self._intPositionX:self._intPositionY+1],self.GetUnitBasisConversions()[0:2,0:2],5,fltGridLength)
        arrTripleLines = objQPoints.FindTriplePoints()
        self.__TripleLineDistanceMatrix = spatial.distance_matrix(arrTripleLines[:,0:2], arrTripleLines[:,0:2])
        arrTripleLines[:,2] = fltMidHeight*np.ones(len(arrTripleLines))
        lstGrainBoundaries = objQPoints.GetGrainBoundaries()
        for i  in range(len(arrTripleLines)):
            arrTripleLines[i] = self.FindNonGrainMean(arrTripleLines[i], fltSearchRadius)
        for j,arrGB in enumerate(lstGrainBoundaries):
            for k in range(len(arrGB)):
                arrPoint = np.array([arrGB[k,0], arrGB[k,1],fltMidHeight])
                arrPoint =  self.FindNonGrainMean(arrPoint, fltSearchRadius)
                arrPoint[2] = fltMidHeight
                lstGrainBoundaries[j][k] = arrPoint
            lstGrainBoundaryObjects.append(gl.GrainBoundary(lstGrainBoundaries[j]))
        arrTripleLines[:,2] = fltMidHeight*np.ones(len(arrTripleLines))
        self.__GrainBoundaries = lstGrainBoundaryObjects
        self.__TripleLines = arrTripleLines 
        return arrTripleLines
    def GetGrainBoundaries(self, intValue = None):
        if intValue is None:
            return self.__GrainBoundaries
        else:
            return self.__GrainBoundaries[intValue]
    def GetNumberOfTripleLines(self)->int:
        return len(self.__TripleLines)
    def GetTripleLines(self, intValue = None)->np.array:
        if intValue is None:
            return self.__TripleLines
        else:
            return self.__TripleLines[intValue]
    def GetNeighbouringGrainBoundaries(self, intTripleLine: int):
        lstDistances = [] #the closest distance 
        lstPositions = []
        arrTripleLine = self.__TripleLines[intTripleLine]
        for arrGB in self.__GrainBoundaries:
            lstTemporary = []
            for j in arrGB.GetPoints(): 
                lstTemporary.append(self.PeriodicMinimumDistance(j ,arrTripleLine))
            lstDistances.append(np.min(lstTemporary))
        for k in range(3):
            lstPositions.append(gf.FindNthSmallestPosition(lstDistances,k))
        return lstPositions
    def GetGrainBoundaryDirection(self, intGrainBoundary:int, intTripleLine: int):
        fltStart = self.PeriodicMinimumDistance(self.__GrainBoundaries[intGrainBoundary].GetPoints(0), self.__TripleLines[intTripleLine])
        fltEnd = self.PeriodicMinimumDistance(self.__GrainBoundaries[intGrainBoundary].GetPoints(-1), self.__TripleLines[intTripleLine])
        vctDirection = self.__GrainBoundaries[intGrainBoundary].GetLinearDirection()
        if fltEnd < fltStart:
            vctDirection = -vctDirection
        return vctDirection
    def FindThreeGrainStrips(self, intTripleLine: int,fltWidth: float, fltIncrement: float):
        lstNeighbouringGB = self.GetNeighbouringGrainBoundaries(intTripleLine)
        lstOfVectors = [] #unit vectors that bisect the grain boundary directions
        lstValues = []
        lstRadii = []
        lstIndices  = []
        fltClosest = np.sort(self.__TripleLineDistanceMatrix[intTripleLine])[1]
        intMax = np.floor(fltClosest/(2*fltIncrement)).astype('int')
        for intV in range(3):
            #lstOfVectors.append(self.GetGrainBoundaryDirection(lstNeighbouringGB[intV],intTripleLine))
            lstOfVectors.append(gf.NormaliseVector(np.mean(self.GetGrainBoundaries(lstNeighbouringGB[intV]).GetPoints(),axis=0)-self.__TripleLines[intTripleLine]))
        for j in range(1,intMax):
            r = fltIncrement*j
            lstRadii.append(r)
            for kVector in range(len(lstOfVectors)):
                v = gf.NormaliseVector(lstOfVectors[np.mod(kVector,3)] + lstOfVectors[np.mod(kVector+1,3)])
                lstIndices.extend(self.FindBoxAtoms(self.GetAtomData()[:,0:4],
                                                           self.__TripleLines[intTripleLine],r*v, 
                                                           fltWidth*np.cross(v,np.array([0,0,1])),np.array([0,0,self.CellHeight])))
                lstIndices = list(np.unique(lstIndices))
            lstValues.append(np.mean(self.GetAtomsByID(lstIndices)[:,self._intPE],axis=0))
        return lstRadii, lstValues,lstIndices    


    
class QuantisedRectangularPoints(object): #linear transform parallelograms into a rectangular parameter space
    def __init__(self, in2DPoints: np.array, inUnitBasisVectors: np.array, n: int, fltGridSize: float):
        self.__WrapperWidth = n
        self.__BasisVectors = inUnitBasisVectors
        self.__InverseMatrix =  np.linalg.inv(inUnitBasisVectors)
        self.__GridSize = fltGridSize
        arrPoints =  np.matmul(in2DPoints, self.__BasisVectors)*(1/fltGridSize)
        #arrPoints[:,0] = np.linalg.norm(inBasisVectors[0]/fltGridSize, axis=0)*arrPoints[:,0]
        #arrPoints[:,1] = np.linalg.norm(inBasisVectors[1]/fltGridSize, axis=0)*arrPoints[:,1]
        intMaxHeight = np.ceil(np.max(arrPoints[:,0])).astype('int')
        intMaxWidth = np.ceil(np.max(arrPoints[:,1])).astype('int')
        self.__ArrayGrid =  np.zeros([(intMaxHeight+1),intMaxWidth+1])
        arrPoints = np.round(arrPoints).astype('int')
        for j in arrPoints:
            self.__ArrayGrid[j[0],j[1]] = 1 #this array represents the simultion cell
        self.__ExtendedArrayGrid = np.zeros([np.shape(self.__ArrayGrid)[0]+2*n,np.shape(self.__ArrayGrid)[1]+2*n])
        self.__ExtendedArrayGrid[n:-n, n:-n] = self.__ArrayGrid
        self.__ExtendedArrayGrid[1:n+1, n:-n] = self.__ArrayGrid[-n:,:]
        self.__ExtendedArrayGrid[-n-1:-1, n:-n] = self.__ArrayGrid[:n,:]
        self.__ExtendedArrayGrid[:,1:n+1] = self.__ExtendedArrayGrid[:,-2*n:-n]
        self.__ExtendedArrayGrid[:,-n-1:-1] = self.__ExtendedArrayGrid[:,n:2*n]
        self.__ExtendedSkeletonGrid = skeletonize(self.__ExtendedArrayGrid).astype('int')
        self.__GrainValue = 0
        self.__GBValue = 1 #just fixed constants used in the array 
        self.__DislocationValue = 2
        self.__TripleLineValue = 3
        self.__TriplePoints = []
        self.__Dislocations = []
        self.__GrainBoundaryLabels = []
        self.__blnGrainBoundaries = False #this flag is set once FindGrainBoundaries() is called
    def GetArrayGrid(self):
        return self.__ArrayGrid
    def GetExtendedArrayGrid(self):
        return self.__ExtendedArrayGrid
    def GetExtendedSkeletonPoints(self):
        return self.__ExtendedSkeletonGrid   
    def ClassifyGBPoints(self,m:int,blnFlagEndPoints = False)-> np.array:
        arrTotal =np.zeros(4*m)
        intLow = int((m-1)/2)
        intHigh = int((m+1)/2)
        arrArgList = np.argwhere(self.__ExtendedSkeletonGrid==self.__GBValue)
        arrCurrent = np.zeros([m,m])
        for x in arrArgList: #loop through the array positions which have GB atoms
            arrCurrent = self.__ExtendedSkeletonGrid[x[0]-intLow:x[0]+intHigh,x[1]-intLow:x[1]+intHigh] #sweep out a m x m square of array positions 
            intSwaps = 0
            if np.shape(arrCurrent) == (m,m): #centre j. This check avoids boundary points
                intValue = arrCurrent[0,0]
                arrTotal[:m ] = arrCurrent[0,:]
                arrTotal[m:2*m] =  arrCurrent[:,-1]
                arrTotal[2*m:3*m] = arrCurrent[-1,::-1]
                arrTotal[3*m:4*m] = arrCurrent[-1::-1,0]
                for k in arrTotal:
                    if (k!= intValue): #the move has changed from grain (int 0) to grain boundary (int 1) or vice versa
                        intSwaps += 1
                        intValue = k
                if intSwaps == 6 and m ==3:
                    if not (arrCurrent[0].all() == self.__GBValue or arrCurrent[-1].all() == self.__GBValue or arrCurrent[:,0].all() == self.__GBValue or  arrCurrent[:,-1].all() ==self.__GBValue):
                        self.SetSkeletonValue(x,self.__TripleLineValue)
                elif intSwaps ==6:
                    self.SetSkeletonValue(x,self.__TripleLineValue)
        #        if intSwaps < 4 and blnFlagEndPoints:
        #            self.SetSkeletonValue(x,self.__DislocationValue)
        #self.__Dislocations = np.argwhere(self.__ExtendedSkeletonGrid == self.__DislocationValue)
        return np.argwhere(self.__ExtendedSkeletonGrid == self.__TripleLineValue)
    def SetSkeletonValue(self,inArray:np.array, intValue: int):
        self.__ExtendedSkeletonGrid[inArray[0], inArray[1]] = intValue
    def __ConvertToCoordinates(self, inArrayPosition: np.array): #takes array position and return real 2D coordinates
        arrPoints = (inArrayPosition - np.ones([2])*self.__WrapperWidth)*self.__GridSize
        arrPoints = np.matmul(arrPoints, self.__InverseMatrix)
        rtnArray = np.zeros([len(arrPoints),3])
        rtnArray[:,0:2] = arrPoints
        return rtnArray
        #return np.matmul())*self.__GridSize,self.__BasisVectors)
    def __ResetSkeletonGrid(self):
        self.__ExtendedSkeletonGrid[self.__ExtendedSkeletonGrid != self.__GrainValue] = self.__GBValue
    def FindTriplePoints(self)->np.array:
        self.__ResetSkeletonGrid()
        self.__TriplePoints = self.ClassifyGBPoints(3, False)
        return self.__ConvertToCoordinates(self.__TriplePoints)
    def FindGrainBoundaries(self)->np.array:
        self.ClassifyGBPoints(5,False)
        k = self.__WrapperWidth 
        arrSkeleton = np.copy(self.__ExtendedSkeletonGrid)
        arrSkeleton[:k,:] = 0
        arrSkeleton[-k:,:] = 0
        arrSkeleton[:,:k] = 0
        arrSkeleton[:,-k:] = 0
        arrSkeleton = (arrSkeleton == self.__GBValue).astype('int')
        self.__GrainBoundaryLabels = label(arrSkeleton)
        self.__NumberOfGrainBoundaries = len(np.unique(self.__GrainBoundaryLabels)) -1
        self.__blnGrainBoundaries = True
    def GetGrainBoundaryLabels(self):
        if  not self.__blnGrainBoundaries:
            self.FindGrainBoundaries()
        return self.__GrainBoundaryLabels
    def GetNumberOfGrainBoundaries(self):
        if not self.__blnGrainBoundaries:
            self.FindGrainBoundaries()
        return self.__NumberOfGrainBoundaries
    def GetGrainBoundaries(self):
        lstGrainBoundaries = []
        lstLineDefects = []
        if not self.__blnGrainBoundaries:
            self.FindGrainBoundaries()
        for j in range(1,self.__NumberOfGrainBoundaries+1): #label 0 is the background
            arrPoints = np.argwhere(self.__GrainBoundaryLabels == j) #find the positions for each label
            if len(arrPoints) > 2:
                lstGrainBoundaries.append(self.__ConvertToCoordinates(arrPoints))
            else:
                lstLineDefects.append(self.__ConvertToCoordinates(arrPoints))
        return lstGrainBoundaries