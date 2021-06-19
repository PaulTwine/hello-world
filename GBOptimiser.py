import numpy as np
import matplotlib.pyplot as plt
import LatticeDefinitions as ld
import GeometryFunctions as gf
import GeneralLattice as gl
import LAMMPSTool as LT
import sys
from mpl_toolkits.mplot3d import Axes3D 
import copy as cp
from scipy import spatial

strDirectory = str(sys.argv[1])
intSigma = int(sys.argv[2])
lstAxis = eval(str(sys.argv[3]))
arrAxis = np.array(lstAxis)
objSigma = gl.SigmaCell(arrAxis,ld.FCCCell)
objSigma.MakeCSLCell(intSigma)
fltAngle1, fltAngle2 = objSigma.GetLatticeRotations()
arrSigmaBasis = objSigma.GetBasisVectors()
intMax = 40
intHeight = 40
s1 = np.linalg.norm(arrSigmaBasis, axis=1)[0]
s2 = np.linalg.norm(arrSigmaBasis, axis=1)[1]
s3 = np.linalg.norm(arrSigmaBasis, axis=1)[2]
a = 4.05 ##lattice parameter
x = np.round(intMax/s1,0)
if np.mod(x,2) !=0: #ensure an even number of CSL unit cells in the x direction
    x += 1
y = np.round(intMax/s2,0)
if np.mod(y,2) !=0: 
    y += 1
w = x*a
l = y*a
h = a*np.round(intHeight/s3,0)
arrX = w*arrSigmaBasis[0]
arrXY = l*arrSigmaBasis[1]
z = h*arrSigmaBasis[2]
if np.all(arrAxis == np.array([1,0,0])):
    arrBasisVectors = gf.StandardBasisVectors(3)
else:
    fltAngle3, arrRotation = gf.FindRotationVectorAndAngle(arrAxis,np.array([0,0,1]))
    arrBasisVectors = gf.RotateVectors(fltAngle3, arrRotation,gf.StandardBasisVectors(3)) 
arrLatticeParameters= np.array([a,a,a])
fltDatum = -3.36
arrShift = a*(0.5-np.random.ranf())*arrSigmaBasis[1]
arrCentre = 0.5*(arrX+arrXY) + arrShift
strConstraint = str(arrXY[0])+ '*(y -' + str(arrCentre[1]) + ') - ' + str(arrXY[1]) + '*(x -' + str(arrCentre[0]) + ')' 
MySimulationCell = gl.SimulationCell(np.array([arrX,arrXY, z])) 
objFullCell1 = gl.ExtrudedParallelogram(arrX,arrXY,s3*h, gf.RotateVectors(fltAngle1,z,arrBasisVectors), ld.FCCCell, arrLatticeParameters,np.zeros(3))
objFullCell2 = gl.ExtrudedParallelogram(arrX,arrXY, s3*h, gf.RotateVectors(fltAngle2,z,arrBasisVectors), ld.FCCCell, arrLatticeParameters,np.zeros(3))
objFullCell1.SetPeriodicity(['n','p','p'])
objFullCell2.SetPeriodicity(['n','p','p'])
objLeftCell1 = cp.deepcopy(objFullCell1)
objLeftCell1.ApplyGeneralConstraint(gf.InvertRegion(strConstraint))
objRightCell2 = cp.deepcopy(objFullCell2)
objRightCell2.ApplyGeneralConstraint(strConstraint)
objBaseLeft = cp.deepcopy(objLeftCell1)
objBaseRight = cp.deepcopy(objRightCell2)
MySimulationCell.AddGrain(objBaseLeft)
MySimulationCell.AddGrain(objBaseRight)
MySimulationCell.RemoveAtomsOnOpenBoundaries()
MySimulationCell.WrapAllAtomsIntoSimulationCell()
MySimulationCell.WriteLAMMPSDataFile(strDirectory + 'read.dat')
lstAtoms, lstPE, fltTolerance = MySimulationCell.LAMMPSMinimisePositions(strDirectory,'read0.dmp','TemplateMin.in',20,fltDatum)
np.savetxt(strDirectory + 'fltCutOff.txt', np.array([fltTolerance]))
