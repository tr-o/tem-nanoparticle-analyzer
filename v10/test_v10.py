import tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
import numpy as np,h5py
from benchmark import tensor_layout,get_slice,read_pair,pixel_metrics,instance_metrics,v8_mask,v9_mask
from fetch_dataset import absolute,select_pair, file_catalog, DOI

class TestEvaluation(unittest.TestCase):
    def test_layouts(self):
        self.assertEqual(tensor_layout((11,512,512)),('nhw',11))
        self.assertEqual(tensor_layout((512,512,11)),('hwn',11))
        self.assertEqual(tensor_layout((11,512,512,1)),('nhwc',11))
        self.assertEqual(tensor_layout((11,1,512,512)),('nchw',11))
        with self.assertRaises(ValueError):tensor_layout((512,512,512))
    def test_hdf5_exact_alignment(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.h5';arr=np.zeros((2,512,512),dtype='uint8')
            arr[0,22:39,98:131]=240
            with h5py.File(p,'w') as f:
                f.create_dataset('images',data=arr)
                f.create_dataset('labels',data=arr//240)
            with h5py.File(p) as f:
                im,gt=read_pair({'images':f['images'],'mode':'nhw'}, {'labels':f['labels'],'mode':'nhw'},0)
                self.assertEqual(int(gt.sum()),17*33)
                self.assertEqual(im[25,100],240)
    def test_nonbinary_floating_labels_fail(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.h5'
            with h5py.File(p,'w') as f:
                f['images']=np.zeros((2,512,512),dtype='float32')
                f['labels']=np.linspace(0,1,2*512*512,dtype='float32').reshape(2,512,512)
            with h5py.File(p) as f:
                with self.assertRaises(ValueError):read_pair({'images':f['images'],'mode':'nhw'}, {'labels':f['labels'],'mode':'nhw'},0)
    def test_metrics(self):
        a=np.zeros((64,64),bool);a[7:20,10:23]=1
        self.assertAlmostEqual(pixel_metrics(a,a)['dice'],1)
        self.assertAlmostEqual(instance_metrics(a,a)['recall'],1)
        b=np.zeros_like(a)
        self.assertEqual(pixel_metrics(b,a)['recall'],0)
        self.assertEqual(instance_metrics(b,a)['recall'],0)
    def test_false_instance(self):
        a=np.zeros((64,64),bool);a[20:35,20:35]=1
        b=np.zeros_like(a);b[44:58,44:58]=1
        self.assertEqual(instance_metrics(b,a)['matched'],0)
    def test_constant_not_particle(self):
        a=np.ones((128,128),np.float32)*0.35
        self.assertFalse(v8_mask(a).any())
        self.assertFalse(v9_mask(a).any())
    def test_invalid_download_host(self):
        with self.assertRaises(ValueError):absolute('https://evil.example/data')
    def test_unique_pair_and_size(self):
        names=['Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_Images.h5','Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_Labels.h5']
        pair=[{'path':x,'size':140000000 if j==0 else 90000000} for j,x in enumerate(names)]
        self.assertEqual(len(select_pair(pair)),2)
        with self.assertRaises(ValueError):select_pair(pair+[pair[0]])
        with self.assertRaises(ValueError):select_pair(pair[:1])

if __name__=='__main__':unittest.main()
