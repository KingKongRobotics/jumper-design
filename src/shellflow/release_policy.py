"""Repository publication defaults; legacy archives remain readable."""
import xml.etree.ElementTree as ET
from .package_io import PackageError

def require_web_appearance(files):
    from .web_appearance import validate_appearance, NAME
    if NAME not in files:
        raise PackageError("Map release requires the be-web/1 appearance standard")
    validate_appearance(files)

RETIRED_MAP_IDS = frozenset({'studio', 'flat', 'obstacles', 'arena'})

def validate_release_policy(kind, manifest, files):
    if kind != 'map':
        return
    ident = manifest['id']
    if ident.startswith('be-'):
        raise PackageError('Map release IDs must not use the be- source prefix')
    if ident in RETIRED_MAP_IDS:
        raise PackageError('This map was retired from the formal library')
    source = manifest.get('source', {})
    if source.get('repository') != 'BE-UNLIMITED/be-unlimited' or ident == 'bedroom':
        require_web_appearance(files)
        return
    export = source.get('visualExport', {})
    if export.get('method') != 'executed-web-scene-graph':
        raise PackageError('BE map release requires the Web visual layer export')
    root = ET.fromstring(files[manifest['world']['file']])
    visuals = [g for g in root.iter('geom') if g.get('name', '').startswith('visual_web_')]
    if not visuals or any(g.get('contype') != '0' or g.get('conaffinity') != '0'
                          or g.get('mass') != '0' for g in visuals):
        raise PackageError('Web visuals must exist and have zero mass and no collision')
    meshes = [g for g in visuals if g.get('type') == 'mesh']
    lines = [g for g in visuals if g.get('name', '').startswith('visual_web_line_')]
    if len(meshes) != export.get('meshBatches') or len(lines) != export.get('lineSegments'):
        raise PackageError('Web visual inventory does not match release provenance')

    require_web_appearance(files)
