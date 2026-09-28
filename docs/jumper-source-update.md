# Jumper baseline

The public reference is robots/jumper/profile.json and its hash-bound source URDF, baseline MJCF and meshes. It contains 41 robot links and 22 movable joints. LM_J0_joint limits are -0.75 to 1 rad. Keep meshes, units, collision geometry, inertia and topology unchanged for appearance-only work.

When updating the baseline, import the matching source revision, compare URDF and native MJCF limits and mesh hashes, and rebuild affected packages against the new profile. Do not edit a hash-bound profile just to change licensing prose; distribution terms are recorded in the repository and package notices. Legacy profiles are not included in this public edition.
