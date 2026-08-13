# Houdini GSplat relighting

![Interim captured-GSplat engineering validation with KineFX and Houdini Groom](../../../../docs/showcase/houdini-honeybee-gsplat-kinefx-groom-contact.png)

Prepare an existing Gaussian Splat for interactive relighting, build its USD
lighting stage, and produce a refined Copernicus image without falling back to
raw Python.

## Workflow

1. `inspect_gsplat_relighting_input` validates the source SOP and required
   point attributes.
2. `prepare_gsplat_sop_chain` reconstructs normals and optionally extracts
   albedo with SideFX Labs.
3. `create_gsplat_relight_lop` creates the Solaris relighting node, camera,
   USD lights, dome light, shadows, and shadow-bias controls. When available it
   also returns a stable relit SOP output with point and attribute evidence.
4. `refresh_gsplat_relight_sop_bridge` rediscovers and force-cooks that bridge
   after Dome or relight parameter changes; callers never depend on a Labs HDA
   internal node path.
5. `create_gsplat_copernicus_raster` rasterizes from the camera and can append
   resolution, sharpen, HSV, gamma, and premultiplication refinements. It can
   also load an absolute HDR/background image and composite GSplats over it via
   the Houdini 22 Blend COP's named `bg` and `fg` inputs.
6. `write_gsplat_copernicus_image` creates or reuses a named `/out` Image ROP,
   renders one frame in the foreground, and reports the freshly written file
   plus existence and byte-size evidence.

The result is a prepared SOP stream, an editable Solaris lighting stage, and a
camera-matched COP output suitable for near-real-time look development.
Use the Image ROP writer for acceptance; node cooking and Viewer caches alone
do not prove that pixels were written to disk.

The linked honeybee media is explicitly an interim engineering validation with
known fixture, anatomy, and LookDev defects. It demonstrates the typed workflow
and must not be presented as final high-fidelity honeybee beauty acceptance.

Requires Houdini 22 and current SideFX Labs GSplat assets. See
[SKILL.md](SKILL.md) for attribute and execution contracts; `tools.yaml`
contains the callable schemas.

The header is real Houdini output from a licensed multiview reconstruction, not
a concept illustration or SideFX sample. Its source record, reconstruction
metrics, hashes, authored-animation disclosure, and known visual limitations
are documented in
[the showcase provenance](../../../../docs/showcase/honeybee-reference-license.md)
and
[`honeybee-gsplat-validation.json`](../../../../docs/showcase/honeybee-gsplat-validation.json).

For trained-checkpoint ingestion, subject cleanup, dark-anatomy retention, and
animation attribute requirements, see the dedicated contract section in
[SKILL.md](SKILL.md). In particular, public validation must not remove black
eyes or legs with a global brightness mask, and checkpoint-specific image
metrics must remain pending until they are freshly measured.
Fixture/label residuals also fail public beauty acceptance and must be checked
from source-camera projections plus a novel view, not hidden by the HDR or crop.
