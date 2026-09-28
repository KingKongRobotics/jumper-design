# Authored challenge maps

Formal files live in `library/maps/`. Three scenes were added and the pouring scene replaced. All packages use `kk-scene-package/2` with a default Jumper, spawn, and robot-free thumbnail.

| Map | Dimensions | Challenge |
|---|---|---|
| Narrow bridge | 2.8 m long, 0.43 m wide, 0.16 m drop | Cross without falling |
| Pouring | Original bottle, cup, and tray on the ground; tabletop and barriers removed | Approach and manipulate props from the ground |
| Shelf maze | 5.2 m square with three alternating shelf rows | Move red, blue, and yellow blocks to matching target zones in order, then reach exit |
| Switchback slopes | Three reversing sections, 0.7 m wide, 0.45 m rise each, 7.13° slope | Pass two turning platforms in order and reach the 1.35 m exit |

Sources are under `library/map-sources/authored/`. Rebuild the three new maps:

```powershell
python scripts/build_authored_challenges.py --sources-only
python scripts/build_ground_pouring.py
```

Then generate and accept Web thumbnails per `docs/web-appearance-standard.md` and package in a fresh candidate directory using `export_map_collection.py --preview-dir`. Source selection prefers authored maps and will not restore the old tabletop pouring version.

Acceptance from this run: all four packages passed native `verify-package`, default whole-robot composition, and spawn checks. Downward ray heights passed at three bridge-center points and three points on each slope. Sampling 100 points per segment on the maze's winding center path gave minimum shelf clearance greater than 0.20 m. Thirteen release-rule and pouring tests passed. Environment thumbnails and whole-robot views were visually inspected, and 12 website download-copy SHAs were checked.

Static path clearance is not a validated dynamic gait. Stage order, scoring, liquid effects, grasping, and movement policy belong to the app. In-package READMEs and named MJCF target areas provide integration points without introducing a mandatory execution protocol.
