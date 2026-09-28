# Public example visual audit

The initial public release retains the environment XML, meshes, materials, visual-appearance declarations and robot-free thumbnails of the four authored examples. Only the nested default robot changes to Jumper Original; native combined loading and spawn checks are repeated during publication. README images are byte-identical to the in-package thumbnails.

The public release review checks all five README images: the complete original robot, park pump track, narrow bridge, shelf maze and switchback slopes. This review does not claim a new end-to-end browser simulator test or policy run. The consumer must verify its supported rendering and physics capabilities; see [the visual standard](web-appearance-standard.md).

When environment visuals change, regenerate the thumbnail through a compatible Web renderer and compare source/imported views at the same camera. A native MuJoCo screenshot alone does not establish Web visual fidelity. Never add a robot to a map thumbnail.
