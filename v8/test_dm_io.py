from pathlib import Path
import unittest
import tempfile,struct
import numpy as np
from dm_io import nm_scale,dm_header_version,select_dataset,area_diameter_nm,resize_scale,robust_preview

class TestDMIngest(unittest.TestCase):
    def test_units_and_noncalibrated(self):
        self.assertAlmostEqual(nm_scale({'units':'Å','scale':2}),.2)
        self.assertAlmostEqual(nm_scale({'units':'um','scale':0.001}),1)
        self.assertIsNone(nm_scale({'units':'pixels','scale':1}))
        self.assertIsNone(nm_scale({'units':'nm','scale':0}))
    def test_header(self):
        with tempfile.NamedTemporaryFile() as f:
            f.write(struct.pack('>I',3)+b'abc');f.flush();self.assertEqual(dm_header_version(f.name),3)
        with tempfile.NamedTemporaryFile() as f:
            f.write(struct.pack('>I',4)+b'abc');f.flush();self.assertEqual(dm_header_version(f.name),4)
        with tempfile.NamedTemporaryFile() as f:
            f.write(b'1234');f.flush()
            with self.assertRaises(ValueError):dm_header_version(f.name)
    def test_select_2d_and_axis_order(self):
        image=np.arange(20*30,dtype=np.uint16).reshape(20,30)
        ds=[dict(data=image,axes=[{'index_in_array':1,'scale':.2,'units':'nm'},
                                   {'index_in_array':0,'scale':4,'units':'Å'}])]
        got,meta=select_dataset(ds)
        self.assertEqual(got.dtype,np.uint16)
        self.assertAlmostEqual(meta['x_nm_per_px'],.2)
        self.assertAlmostEqual(meta['y_nm_per_px'],.4)
        self.assertEqual(meta['calibration_status'],'calibrated')
        self.assertAlmostEqual(area_diameter_nm(100,.2,.4),2*np.sqrt(8/np.pi))
        resized=resize_scale(meta,(20,30),(10,15))
        self.assertAlmostEqual(resized['x_nm_per_px'],.4)
        self.assertAlmostEqual(resized['y_nm_per_px'],.8)
    def test_missing_units_never_guess(self):
        ds=[dict(data=np.ones((20,30)),axes=[{'index_in_array':0,'scale':.2,'units':'nm'},
                                               {'index_in_array':1,'scale':2,'units':'pixel'}])]
        _,meta=select_dataset(ds)
        self.assertEqual(meta['calibration_status'],'missing_or_unsupported_units')
        self.assertIsNone(meta['x_nm_per_px']);self.assertIsNone(meta['y_nm_per_px'])
    def test_ambiguous_and_multiframe(self):
        ds=[dict(data=np.ones((20,20)),axes=[]),dict(data=np.ones((20,30)),axes=[])]
        with self.assertRaisesRegex(ValueError,'dataset-index'):select_dataset(ds)
        stack=[dict(data=np.zeros((2,20,30)),axes=[])]
        with self.assertRaisesRegex(ValueError,'--frame'):select_dataset(stack,index=0)
        x,_=select_dataset(stack,index=0,frame=1);self.assertEqual(x.shape,(20,30))
    def test_preview_no_raw_change(self):
        raw=np.arange(400,dtype=np.uint16).reshape(20,20)
        b=raw.copy();p=robust_preview(raw)
        self.assertTrue(np.array_equal(raw,b));self.assertEqual(p.dtype,np.float32)

if __name__=='__main__':unittest.main()
