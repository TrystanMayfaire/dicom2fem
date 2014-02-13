#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DICOM2FEM - organ segmentation and FE model generator

Example:

$ dicom2fem -d sample_data
"""
#TODO:
# recalculate voxelsize when rescaled

# import unittest
from optparse import OptionParser
from scipy.io import loadmat, savemat
from scipy import ndimage
import numpy as np
import sys
import os

from PyQt4.QtGui import QApplication, QMainWindow, QWidget,\
     QGridLayout, QLabel, QPushButton, QFrame, QFileDialog,\
     QFont, QInputDialog, QComboBox

sys.path.append("./pyseg_base/src/")

import dcmreaddata as dcmreader
from seed_editor_qt import QTSeedEditor
import pycut
from meshio import supported_capabilities, supported_formats, MeshIO
from seg2fem import gen_mesh_from_voxels, gen_mesh_from_voxels_mc
from seg2fem import smooth_mesh

from viewer import QVTKViewer

inv_supported_formats = dict(zip(supported_formats.values(),
                                 supported_formats.keys()))
smooth_methods = {
    'taubin vol.': (smooth_mesh, {'n_iter': 10, 'volume_corr': True,
                             'lam': 0.6307, 'mu': -0.6347}),
    'taubin': (smooth_mesh, {'n_iter': 10, 'volume_corr': False,
                             'lam': 0.6307, 'mu': -0.6347}),

    }

mesh_generators = {
    'surf/tri': (gen_mesh_from_voxels, {'etype': 't', 'mtype': 's'}),
    'surf/quad': (gen_mesh_from_voxels, {'etype': 'q', 'mtype': 's'}),
    'vol/tetra': (gen_mesh_from_voxels, {'etype': 't', 'mtype': 'v'}),
    'vol/hexa': (gen_mesh_from_voxels, {'etype': 'q', 'mtype': 'v'}),
    'marching cubes': (gen_mesh_from_voxels_mc, {}),
    }

elem_tab = {
    '2_3': 'triangles',
    '3_4': 'tetrahedrons',
    '2_4': 'quads',
    '3_8': 'hexahedrons'
    }

class MainWindow(QMainWindow):

    def __init__(self, dcmdir=None):
        QMainWindow.__init__(self)

        self.dcmdir = dcmdir
        self.dcm_3Ddata = None
        self.dcm_metadata = None
        self.dcm_zoom = None
        self.dcm_offsetmm = np.array([0,0,0])
        self.voxel_volume = 0.0
        self.voxel_sizemm = None
        self.segmentation_seeds = None
        self.segmentation_data = None
        self.mesh_data = None
        self.mesh_out_format = 'vtk'
        self.mesh_smooth_method = 'taubin'
        self.initUI()

    def initUI(self):

        cw = QWidget()
        self.setCentralWidget(cw)
        grid = QGridLayout()
        grid.setSpacing(15)

        # status bar
        self.statusBar().showMessage('Ready')

        font_label = QFont()
        font_label.setBold(True)

        ################ dicom reader
        rstart = 0
        text_dcm = QLabel('DICOM reader')
        text_dcm.setFont(font_label)
        self.text_dcm_dir = QLabel('DICOM dir:')
        self.text_dcm_data = QLabel('DICOM data:')
        self.text_dcm_out = QLabel('output file:')
        grid.addWidget(text_dcm, rstart + 0, 1, 1, 4)
        grid.addWidget(self.text_dcm_dir, rstart + 1, 1, 1, 4)
        grid.addWidget(self.text_dcm_data, rstart + 2, 1, 1, 4)
        grid.addWidget(self.text_dcm_out, rstart + 3, 1, 1, 4)

        btn_dcmdir = QPushButton("Load DICOM", self)
        btn_dcmdir.clicked.connect(self.loadDcmDir)
        btn_dcmred = QPushButton("Reduce", self)
        btn_dcmred.clicked.connect(self.reduceDcm)
        btn_dcmcrop = QPushButton("Crop", self)
        btn_dcmcrop.clicked.connect(self.cropDcm)
        btn_dcmsave = QPushButton("Save DCM", self)
        btn_dcmsave.clicked.connect(self.saveDcm)
        grid.addWidget(btn_dcmdir, rstart + 4, 1)
        grid.addWidget(btn_dcmred, rstart + 4, 2)
        grid.addWidget(btn_dcmcrop, rstart + 4, 3)
        grid.addWidget(btn_dcmsave, rstart + 4, 4)

        hr = QFrame()
        hr.setFrameShape(QFrame.HLine)
        grid.addWidget(hr, rstart + 5, 0, 1, 6)

        ################ segmentation
        rstart = 6
        text_seg = QLabel('Segmentation')
        text_seg.setFont(font_label)
        self.text_seg_in = QLabel('input data:')
        self.text_seg_data = QLabel('segment. data:')
        self.text_seg_out = QLabel('output file:')
        grid.addWidget(text_seg, rstart + 0, 1)
        grid.addWidget(self.text_seg_in, rstart + 1, 1, 1, 4)
        grid.addWidget(self.text_seg_data, rstart + 2, 1, 1, 4)
        grid.addWidget(self.text_seg_out, rstart + 3, 1, 1, 4)

        btn_segload = QPushButton("Load DCM", self)
        btn_segload.clicked.connect(self.loadDcm)
        btn_segauto = QPushButton("Automatic seg.", self)
        btn_segauto.clicked.connect(self.autoSeg)
        btn_segman = QPushButton("Manual seg.", self)
        btn_segman.clicked.connect(self.manualSeg)
        btn_segsave = QPushButton("Save SEG", self)
        btn_segsave.clicked.connect(self.saveSeg)
        grid.addWidget(btn_segload, rstart + 4, 1)
        grid.addWidget(btn_segauto, rstart + 4, 2)
        grid.addWidget(btn_segman, rstart + 4, 3)
        grid.addWidget(btn_segsave, rstart + 4, 4)

        hr = QFrame()
        hr.setFrameShape(QFrame.HLine)
        grid.addWidget(hr, rstart + 5, 0, 1, 6)

        ################ mesh gen.
        rstart = 12
        text_mesh = QLabel('Mesh generation')
        text_mesh.setFont(font_label)
        self.text_mesh_in = QLabel('input data:')
        self.text_mesh_data = QLabel('mesh data:')
        self.text_mesh_out = QLabel('output file:')
        grid.addWidget(text_mesh, rstart + 0, 1)
        grid.addWidget(self.text_mesh_in, rstart + 1, 1, 1, 4)
        grid.addWidget(self.text_mesh_data, rstart + 2, 1, 1, 4)
        grid.addWidget(self.text_mesh_out, rstart + 3, 1, 1, 4)

        btn_meshload = QPushButton("Load SEG", self)
        btn_meshload.clicked.connect(self.loadSeg)
        btn_meshsave = QPushButton("Save MESH", self)
        btn_meshsave.clicked.connect(self.saveMesh)
        btn_meshgener = QPushButton("Generate", self)
        btn_meshgener.clicked.connect(self.generMesh)
        btn_meshsmooth = QPushButton("Smooth", self)
        btn_meshsmooth.clicked.connect(self.smoothMesh)
        btn_meshview = QPushButton("View", self)
        btn_meshview.clicked.connect(self.viewMesh)
        grid.addWidget(btn_meshload, rstart + 4, 1)
        grid.addWidget(btn_meshgener, rstart + 4, 2)
        grid.addWidget(btn_meshsmooth, rstart + 4, 3)
        grid.addWidget(btn_meshsave, rstart + 4, 4)
        grid.addWidget(btn_meshview, rstart + 8, 2, 1, 2)

        text_mesh_mesh = QLabel('mesh generator:')
        text_mesh_smooth = QLabel('smooth method:')
        text_mesh_output = QLabel('output format:')
        grid.addWidget(text_mesh_mesh, rstart + 6, 2)
        grid.addWidget(text_mesh_smooth, rstart + 6, 3)
        grid.addWidget(text_mesh_output, rstart + 6, 4)

        combo_mg = QComboBox(self)
        combo_mg.activated[str].connect(self.changeMesh)
        self.mesh_generator = 'marching cubes'
        keys = mesh_generators.keys()
        keys.sort()
        combo_mg.addItems(keys)
        combo_mg.setCurrentIndex(keys.index(self.mesh_generator))
        grid.addWidget(combo_mg, rstart + 7, 2)

        combo_sm = QComboBox(self)
        combo_sm.activated[str].connect(self.changeOut)

        supp_write = []
        for k, v in supported_capabilities.iteritems():
            if 'w' in v:
                supp_write.append(k)

        combo_sm.addItems(supp_write)
        combo_sm.setCurrentIndex(supp_write.index('vtk'))
        grid.addWidget(combo_sm, rstart + 7, 4)

        combo_out = QComboBox(self)
        combo_out.activated[str].connect(self.changeSmoothMethod)
        keys = smooth_methods.keys()
        combo_out.addItems(keys)
        combo_out.setCurrentIndex(keys.index('taubin'))
        grid.addWidget(combo_out, rstart + 7, 3)

        hr = QFrame()
        hr.setFrameShape(QFrame.HLine)
        grid.addWidget(hr, rstart + 9, 0, 1, 6)

        # quit
        btn_quit = QPushButton("Quit", self)
        btn_quit.clicked.connect(self.quit)
        grid.addWidget(btn_quit, 24, 2, 1, 2)

        cw.setLayout(grid)
        self.setWindowTitle('DICOM2FEM')
        self.show()

    def quit(self, event):
        self.close()

    def setLabelText(self, obj, text):
        dlab = str(obj.text())
        obj.setText(dlab[:dlab.find(':')] + ': %s' % text)

    def getDcmInfo(self):
        vsize = tuple([float(ii) for ii in self.voxel_sizemm])
        ret = ' %dx%dx%d,  %fx%fx%f mm' % (self.dcm_3Ddata.shape + vsize)

        return ret

    def setVoxelVolume(self, vxs):
        self.voxel_volume = np.prod(vxs)

    def loadDcmDir(self):
        self.statusBar().showMessage('Reading DICOM directory...')
        QApplication.processEvents()

        if self.dcmdir is None:
            self.dcmdir = dcmreader.get_dcmdir_qt(app=True)

        if self.dcmdir is not None:
            dcr = dcmreader.DicomReader(os.path.abspath(self.dcmdir),
                                        qt_app=self)
        else:
            self.statusBar().showMessage('No DICOM directory specified!')
            return

        if dcr.validData():
            self.dcm_3Ddata = dcr.get_3Ddata()
            self.dcm_metadata = dcr.get_metaData()
            self.voxel_sizemm = np.array(self.dcm_metadata['voxelsize_mm'])
            self.setVoxelVolume(self.voxel_sizemm)
            self.setLabelText(self.text_dcm_dir, self.dcmdir)
            self.setLabelText(self.text_dcm_data, self.getDcmInfo())
            self.statusBar().showMessage('Ready')
            self.setLabelText(self.text_seg_in, 'DICOM reader')

        else:
            self.statusBar().showMessage('No DICOM data in direcotry!')

    def reduceDcm(self, event=None, factor=None, default=(0.5,0.5,0.5)):
        if self.dcm_3Ddata is None:
            self.statusBar().showMessage('No DICOM data!')
            return

        self.statusBar().showMessage('Reducing DICOM data...')
        QApplication.processEvents()

        if factor is None:
            value, ok = QInputDialog.getText(self, 'Reduce DICOM data',
                                             'Reduce factors (RZ,RX,RY) [0-1.0]:',
                                             text='%.2f,%.2f,%.2f' % default)
            if ok:
                vals = value.split(',')
                if len(vals) == 3:
                    factor = [float(ii) for ii in vals]

                else:
                    aux = float(vals[0])
                    factor = [aux, aux, aux]

        self.dcm_zoom = np.array(factor)
        for ii in factor:
           if ii < 0.0 or ii > 1.0:
               self.dcm_zoom = None

        if self.dcm_zoom is not None:
            self.dcm_3Ddata = ndimage.zoom(self.dcm_3Ddata, self.dcm_zoom,
                                           prefilter=False, mode='nearest')
            self.voxel_sizemm = self.voxel_sizemm / self.dcm_zoom
            self.setLabelText(self.text_dcm_data, self.getDcmInfo())

            self.statusBar().showMessage('Ready')

        else:
            self.statusBar().showMessage('No valid reduce factor!')

    def cropDcm(self):
        if self.dcm_3Ddata is None:
            self.statusBar().showMessage('No DICOM data!')
            return

        self.statusBar().showMessage('Cropping DICOM data...')
        QApplication.processEvents()

        pyed = QTSeedEditor(self.dcm_3Ddata, mode='crop',
                            voxelSize=self.voxel_sizemm)
        pyed.exec_()
        self.dcm_3Ddata = pyed.getImg()
        self.dcm_offsetmm = pyed.getOffset()

        self.setLabelText(self.text_dcm_data, self.getDcmInfo())
        self.statusBar().showMessage('Ready')

        self.statusBar().showMessage('Ready')

    def saveDcm(self, event=None, filename=None):
        if self.dcm_3Ddata is not None:
            self.statusBar().showMessage('Saving DICOM data...')
            QApplication.processEvents()

            if filename is None:
                filename = \
                    str(QFileDialog.getSaveFileName(self,
                                                    'Save DCM file',
                                                    filter='Files (*.dcm)'))
            if len(filename) > 0:
                savemat(filename, {'data': self.dcm_3Ddata,
                                   'voxelsize_mm': self.voxel_sizemm,
                                   'offset_mm': self.dcm_offsetmm},
                                   appendmat=False)

                self.setLabelText(self.text_dcm_out, filename)
                self.statusBar().showMessage('Ready')

            else:
                self.statusBar().showMessage('No output file specified!')

        else:
            self.statusBar().showMessage('No DICOM data!')

    def loadDcm(self, event=None, filename=None):
        self.statusBar().showMessage('Loading DICOM data...')
        QApplication.processEvents()

        if filename is None:
            filename = str(QFileDialog.getOpenFileName(self, 'Load DCM file',
                                                       filter='Files (*.dcm)'))

        if len(filename) > 0:

            data = loadmat(filename,
                           variable_names=['data', 'voxelsize_mm', 'offset_mm'],
                           appendmat=False)

            self.dcm_3Ddata = data['data']
            self.voxel_sizemm = data['voxelsize_mm'].reshape((3,1))
            self.dcm_offsetmm = data['offset_mm'].reshape((3,1))
            self.setVoxelVolume(self.voxel_sizemm.reshape((3,)))
            self.setLabelText(self.text_seg_in, filename)
            self.statusBar().showMessage('Ready')

        else:
            self.statusBar().showMessage('No input file specified!')

    def checkSegData(self):
        if self.segmentation_data is None:
            self.statusBar().showMessage('No SEG data!')
            return

        nzs = self.segmentation_data.nonzero()
        nn = nzs[0].shape[0]
        if nn > 0:
            aux = ' voxels = %d, volume = %.2e mm3' % (nn, nn * self.voxel_volume)
            self.setLabelText(self.text_seg_data, aux)
            self.setLabelText(self.text_mesh_in, 'segmentation data')
            self.statusBar().showMessage('Ready')

        else:
            self.statusBar().showMessage('Zero SEG data!')

    def autoSeg(self):
        if self.dcm_3Ddata is None:
            self.statusBar().showMessage('No DICOM data!')
            return

        igc = pycut.ImageGraphCut(self.dcm_3Ddata,
                                  voxelsize=self.voxel_sizemm)

        pyed = QTSeedEditor(self.dcm_3Ddata,
                            seeds=self.segmentation_seeds,
                            modeFun=igc.interactivity_loop,
                            voxelSize=self.voxel_sizemm)
        pyed.exec_()

        self.segmentation_data = pyed.getContours()
        self.segmentation_seeds = pyed.getSeeds()
        self.checkSegData()

    def manualSeg(self):
        if self.dcm_3Ddata is None:
            self.statusBar().showMessage('No DICOM data!')
            return

        pyed = QTSeedEditor(self.dcm_3Ddata,
                            seeds=self.segmentation_data,
                            mode='draw',
                            voxelSize=self.voxel_sizemm)
        pyed.exec_()

        self.segmentation_data = pyed.getSeeds()
        self.checkSegData()

    def saveSeg(self, event=None, filename=None):
        if self.segmentation_data is not None:
            self.statusBar().showMessage('Saving segmentation data...')
            QApplication.processEvents()

            if filename is None:
                filename = \
                    str(QFileDialog.getSaveFileName(self,
                                                    'Save SEG file',
                                                    filter='Files (*.seg)'))

            if len(filename) > 0:

                outdata = {'data': self.dcm_3Ddata,
                           'segdata': self.segmentation_data,
                           'voxelsize_mm': self.voxel_sizemm,
                           'offset_mm': self.dcm_offsetmm}

                if self.segmentation_seeds is not None:
                    outdata['segseeds'] = self.segmentation_seeds

                savemat(filename, outdata, appendmat=False)
                self.setLabelText(self.text_seg_out, filename)
                self.statusBar().showMessage('Ready')

            else:
                self.statusBar().showMessage('No output file specified!')

        else:
            self.statusBar().showMessage('No segmentation data!')

    def loadSeg(self, event=None, filename=None):
        if filename is None:
            filename = str(QFileDialog.getOpenFileName(self, 'Load SEG file',
                                                       filter='Files (*.seg)'))

        if len(filename) > 0:
            self.statusBar().showMessage('Loading segmentation data...')
            QApplication.processEvents()

            data = loadmat(filename,
                           variable_names=['data', 'segdata', 'segseeds',
                                           'voxelsize_mm', 'offset_mm'],
                           appendmat=False)

            self.dcm_3Ddata = data['data']
            self.segmentation_data = data['segdata']
            if 'segseeds' in data:
                self.segmentation_seeds = data['segseeds']

            else:
                self.segmentation_seeds = None

            self.voxel_sizemm = data['voxelsize_mm'].reshape((3,1))
            self.dcm_offsetmm = data['offset_mm'].reshape((3,1))
            self.setVoxelVolume(self.voxel_sizemm.reshape((3,)))
            self.setLabelText(self.text_mesh_in, filename)
            self.statusBar().showMessage('Ready')

        else:
            self.statusBar().showMessage('No input file specified!')

    def saveMesh(self, event=None, filename=None):
        if self.mesh_data is not None:
            self.statusBar().showMessage('Saving mesh...')
            QApplication.processEvents()

            if filename is None:
                file_ext = inv_supported_formats[self.mesh_out_format]
                filename = \
                    str(QFileDialog.getSaveFileName(self, 'Save MESH file',
                                                    filter='Files (*%s)'\
                                                        % file_ext))

            if len(filename) > 0:

                io = MeshIO.for_format(filename, format=self.mesh_out_format,
                                       writable=True)
                io.write(filename, self.mesh_data)

                self.setLabelText(self.text_mesh_out, filename)
                self.statusBar().showMessage('Ready')

            else:
                self.statusBar().showMessage('No output file specified!')

        else:
            self.statusBar().showMessage('No mesh data!')

    def generMesh(self):

        self.statusBar().showMessage('Generating mesh...')
        QApplication.processEvents()

        if self.segmentation_data is not None:
            gen_fun, pars = mesh_generators[self.mesh_generator]
            self.mesh_data = gen_fun(self.segmentation_data,
                                     self.voxel_sizemm * 1.0e-3,
                                     **pars)

            self.mesh_data.coors += self.dcm_offsetmm.reshape((1,3)) * 1.0e-3

            self.setLabelText(self.text_mesh_data, '%d %s'\
                                  % (self.mesh_data.n_el,
                                     elem_tab[self.mesh_data.descs[0]]))

            self.statusBar().showMessage('Ready')

        else:
            self.statusBar().showMessage('No segmentation data!')

    def smoothMesh(self):
        self.statusBar().showMessage('Smoothing mesh...')
        QApplication.processEvents()

        if self.mesh_data is not None:
            smooth_fun, pars = smooth_methods[self.mesh_smooth_method]
            self.mesh_data.coors = smooth_fun(self.mesh_data, **pars)

            self.setLabelText(self.text_mesh_data,
                              '%d %s, smooth method - %s'\
                                  % (self.mesh_data.n_el,
                                     elem_tab[self.mesh_data.descs[0]],
                                     self.mesh_smooth_method))

            self.statusBar().showMessage('Ready')

        else:
            self.statusBar().showMessage('No mesh data!')

    def viewMesh(self):
        if self.mesh_data is not None:
            vtk_file = 'mesh_geom.vtk'
            self.mesh_data.write(vtk_file)
            view = QVTKViewer(vtk_file)
            view.exec_()

        else:
            self.statusBar().showMessage('No mesh data!')

    def changeMesh(self, val):
        self.mesh_generator = str(val)

    def changeOut(self, val):
        self.mesh_out_format = str(val)

    def changeSmoothMethod(self, val):
        self.mesh_smooth_method = str(val)

usage = '%prog [options]\n' + __doc__.rstrip()
help = {
    'dcm_dir': 'DICOM data direcotory',
    'dcm_file': 'DCM file with DICOM data',
    'seg_file': 'file with segmented data',
}

def main():
    parser = OptionParser(description='DICOM2FEM')
    parser.add_option('-d','--dcmdir', action='store',
                      dest='dcmdir', default=None,
                      help=help['dcm_dir'])
    parser.add_option('-f','--dcmfile', action='store',
                      dest='dcmfile', default=None,
                      help=help['dcm_file'])
    parser.add_option('-s','--segfile', action='store',
                      dest='segfile', default=None,
                      help=help['seg_file'])

    (options, args) = parser.parse_args()

    app = QApplication(sys.argv)
    mw = MainWindow(dcmdir=options.dcmdir)

    if options.dcmdir is not None:
        mw.loadDcmDir()

    if options.dcmfile is not None:
        mw.loadDcm(filename=options.dcmfile)

    if options.segfile is not None:
        mw.loadSeg(filename=options.segfile)

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
