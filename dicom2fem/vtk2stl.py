#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os
import vtk

def vtk2stl(fn_in, fn_out):

    reader = vtk.vtkDataSetReader()
    reader.SetFileName(fn_in)
    reader.Update()

    gfilter = vtk.vtkGeometryFilter()
    gfilter.SetInputData(reader.GetOutput())

    writer = vtk.vtkSTLWriter()
    writer.SetFileName(fn_out)
    writer.SetInputData(gfilter.GetOutput())
    writer.Write()

def main():
    fname, ext = os.path.splitext(sys.argv[1])
    vtk2stl('%s.vtk' % fname, '%s.stl' % fname)

if __name__ == "__main__":
    main()
