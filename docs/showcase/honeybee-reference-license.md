# Honeybee showcase provenance and limits

## Captured GSplat engineering validation

The current captured-data validation uses specimen `UCSB-IZC00037044` from
the University of California, Santa Barbara dataset
[Honey Bee Heat Budget Images and Models](https://doi.org/10.5281/zenodo.17823483).
The Zenodo record is licensed under CC BY 4.0. The published multiview contact
sheet is included with attribution; no private or uncleared user photograph is
committed. The showcase contact sheet arranges and scales eight licensed source
views on one canvas; it does not replace the source record or its license.

The reconstruction was solved with COLMAP and trained with Nerfstudio
Splatfacto. A deterministic geometric pass removed the specimen-pin region:
75,746 source Gaussians became 70,269 retained Gaussians. This operation
deletes fitted regions and does not infer or synthesize hidden anatomy. The
preview evaluation records PSNR 21.90895, SSIM 0.84895, and LPIPS 0.14534.
Hashes, camera conventions, thresholds, and artifact disclosures are preserved
in [`honeybee-gsplat-validation.json`](honeybee-gsplat-validation.json).

The Houdini animation and fur are downstream authored layers. KineFX does not
turn the pinned specimen into captured biological motion, and Houdini Groom
curves are not photographed strands. The outdoor environment is presentation
lighting, not part of the source capture. Residual support Gaussians and
occluded or incomplete legs, antennae, claws, and wing edges prevent final
beauty acceptance.

The real Houdini UI evidence has only its title bar cropped to remove a local
path. The application chrome below it, Scene View, parameter editor, timeline,
and node graph are unmodified.

## Archived procedural rig validation

The animated asset in this showcase is an original DCC-MCP procedural model.
It is assembled from authored polygonal forms, curves, materials, and KineFX
animation. It is not a SideFX sample, photogrammetry reconstruction, CT mesh,
or trained Gaussian Splat.

## Published anatomy reference

The first panel uses a lateral *Apis mellifera* worker photograph from the USGS
Bee Inventory and Monitoring Lab. It is a United States government work made
available in the public domain:

- [Apis mellifera, light body, side, Beltsville, Maryland](https://commons.wikimedia.org/wiki/File:Apis_mellifera,_light_body,_side,_beltsville,_md_2017-05-26-15.27_(34717464480).jpg)

The public showcase embeds only this clearly licensed reference. No private or
uncleared user photograph is committed.

## Lighting

The flight render uses Poly Haven's
[Residential Garden](https://polyhaven.com/a/residential_garden) HDRI under the
CC0 license. It is the only environment emitter in the shot.

## Verified technical evidence

- 96 frames at 1280×720 and 24 fps, rendered with Karma and displayed through
  the Houdini 22 ACES configuration.
- Six procedural leg hierarchies with authored tarsus, pad, and claw controls.
- Per-frame hierarchy checks keep the tested controls at or above Z=-0.003;
  this is not a substitute for per-primitive collision or contact solving.
- One bee instance is rendered; body motion blur is disabled to avoid apparent
  duplicate silhouettes.
- The Houdini UI captures are real and are not recreated product interfaces,
  but the current framing does not show the complete asset and readable node
  graph together. They are retained as internal validation evidence and are not
  presented as the final public UI acceptance frame.

## Known limitations

The current thorax, head, abdomen, legs, and wings are stylized procedural
approximations. The silhouette reads closer to an ant-like generic insect than
to the public *Apis mellifera* reference. The head/thorax/abdomen proportions,
compound eyes, wing planform and venation, leg segmentation, tarsi, claws, and
abdomen termination all require reconstruction-level replacement. Higher
subdivision and denser groom curves do not correct those anatomical errors.

The current body compliance is phase-delayed authored motion, not a biological
soft-body simulation. Eye motion is a head/attention control, not compound-eye
deformation. The garden render is also too dark for final LookDev acceptance.

The next reconstruction stage is deliberately separate: train a real honeybee
Gaussian Splat from a licensed multi-view capture, validate its provenance,
deform it with the GSplat-aware KineFX tools, and generate fur with the Houdini
Groom workflow. Until that evidence exists, this procedural asset must not be
labelled as a real GSplat reconstruction.
