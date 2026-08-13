# Procedural rig validation provenance and limits

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
