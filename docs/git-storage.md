# Repository storage

Code, schemas, docs and indexes use ordinary Git. Selected .skin/.map files, robot meshes and authored-scene binary resources use Git LFS. Formal packages live directly in library/skins and library/maps and contain their own thumbnails. README illustrations are documentation copies of those embedded thumbnails.

The public release excludes private history, character appearances, manufacturing deliverables and old robot libraries. Keep outputs/, workspaces/, .local/ and credentials ignored. Do not remove license notices when exporting or repacking. A clone needs Git LFS payloads before integration tests or native simulation; `git lfs pull` and `git lfs fsck` verify local availability.
