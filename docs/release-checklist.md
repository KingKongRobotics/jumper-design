# Release verification

1. Verify provenance and licenses for included materials and nested package assets. Do not add character assets or private history to this public edition.
2. Run `python -m pytest tests -q`, `python scripts/check_english.py --require-packages`, `python scripts/check_publish.py --json`, and `git lfs fsck`.
3. Verify every indexed package against robots/jumper/profile.json with native MuJoCo enabled. Compare index hashes and embedded previews. The four map examples use jumper-original as their default robot.
4. Review environment thumbnails without robots and separately inspect composed robot visibility and spawn. Preserve the original visual files when replacing only the default robot.
5. Build the Python wheel and check that Apache-2.0 metadata and LICENSE/NOTICE files are present.
6. Clone into a new directory, fetch LFS payloads, repeat package and installation checks, and compare package hashes. Push only after local checks pass; verify the remote commit and a fresh remote clone afterwards.

Native model loading and static visual review are not physical-fit or controller-performance certification. CI configuration alone is not evidence that remote jobs passed.
