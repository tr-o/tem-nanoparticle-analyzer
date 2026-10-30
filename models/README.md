# Model registry

Only two **serialized** models are shipped. The filenames represent training provenance, **not an ordering of accuracy**.

| Model file | Training data | Intended use | Important limitation |
|---|---|---|---|
| `synthetic_rf.joblib` | 16 synthetic BF-TEM images | Demo and synthetic verification | Never validated as a reliable real-TEM particle counter |
| `weak_tem_rf.joblib` | Synthetic TEM + weak labels from a few Pt/Ag images | Exploratory v2/v4 comparisons | No independent expert GT assessment of generalization |

**v13/v15 are separate supervised boundary-segmentation experiments on EMPS TEM/SEM data**. The v15 experiment reported F1 improvements when increasing labeled training images, but there is **no v15 production-ready serialized model in this repository**. Neither shipped RF should be described as having v15's benchmark performance.

Model promotion policy: train/test IDs and image provenance, serialized estimator and dependency versions, calibration assumptions, per-image matched-instance scores, independent test report and example overlays must be recorded before a model becomes a supported default.

Loading `.joblib` files can execute arbitrary code; only load models from a trusted source.
