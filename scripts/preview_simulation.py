#!/usr/bin/env python3
"""Load a portable robot through MuJoCo VFS, including Unicode Windows paths."""
from pathlib import Path
import argparse
import struct
import zlib
import time


def load_package(path):
    import mujoco
    path = Path(path).resolve()
    model_path = path / 'scene.xml'
    assets = {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob('*')
              if p.is_file() and p.suffix.lower() in {'.xml', '.stl', '.obj', '.png'}}
    return mujoco.MjModel.from_xml_string(model_path.read_text(encoding='utf-8'), assets)


def save_png(path, rgb):
    height, width, _ = rgb.shape
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data) & 0xffffffff)
    data = b''.join(b'\0' + row.tobytes() for row in rgb)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0))
                          + chunk(b'IDAT', zlib.compress(data)) + chunk(b'IEND', b''))


def main():
    import mujoco
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', nargs='?', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--render', type=Path)
    parser.add_argument('--simulate', action='store_true', help='Explicitly step the preserved baseline physics')
    parser.add_argument('--view', choices=['front', 'back', 'side', 'three-quarter'], default='three-quarter')
    args = parser.parse_args()
    model = load_package(args.package)
    data = mujoco.MjData(model)
    if model.nkey:
        mujoco.mj_resetDataKeyframe(model, data, 0)
    mujoco.mj_forward(model, data)
    if args.render:
        camera = mujoco.MjvCamera()
        camera.lookat[:] = [0, 0, 0.14]
        camera.distance = 0.8
        camera.elevation = -22
        camera.azimuth = {'front': 180, 'back': 0, 'side': 90, 'three-quarter': 145}[args.view]
        with mujoco.Renderer(model, height=900, width=1200) as renderer:
            renderer.update_scene(data, camera)
            save_png(args.render, renderer.render())
    else:
        import mujoco.viewer
        if args.simulate:
            mujoco.viewer.launch(model, data)
        else:
            # Static inspection: sync camera/UI but do not start a physics thread.
            with mujoco.viewer.launch_passive(model, data) as viewer:
                while viewer.is_running():
                    viewer.sync()
                    time.sleep(1 / 60)


if __name__ == '__main__':
    main()
