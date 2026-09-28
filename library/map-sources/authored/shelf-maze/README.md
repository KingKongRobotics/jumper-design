# Shelf maze

Three alternating rows of shelves create four winding corridors on a 5.2 × 5.2 m field. Straight corridors have at least 1.0 m clear width and end passages have 0.775 m, allowing for 0.385 m static robot width and turning clearance. Shelf bases have solid collision; the robot cannot cut through them.

Complete three stages in order:

1. Move `prop:red` from (-2.02,-1.4) to `target_red` (-0.65,1.35).
2. Move `prop:blue` from (-0.65,0.6) to `target_blue` (0.65,-1.3).
3. Move `prop:yellow` from (0.65,-0.55) to `target_yellow` (2.02,1.3), then reach `exit`.

Each block has 7 cm sides and mass 40 g. Target areas have about 0.42 m inner width. Suggested app success criterion: block center inside target, on the ground, moving slowly for one second. The app implements order, timing, and reset. The package supplies named objects and target sites, but no scoring logic or validated grasp policy. Coordinates are map-local meters; composed names have the `scn_` prefix.
