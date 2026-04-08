#!/usr/bin/env python3
"""
retopo.py — Retopologize a mesh to a target triangle count.

Uses trimesh + fast-simplification for quadric edge collapse decimation.
No pymeshlab dependency (pymeshlab pip builds have broken format plugins).

Usage:
    python retopo.py --input input.glb --output output.glb --target-tris 4000
"""

import argparse
import sys
import os


def retopologize(input_path, output_path, target_tris=4000):
    """
    Decimate mesh to target triangle count with quality preservation.

    Steps:
    1. Load mesh (any format trimesh supports)
    2. Quadric edge collapse decimation to target
    3. Save result
    """
    import trimesh

    # Load mesh
    loaded = trimesh.load(input_path, force='mesh')
    if isinstance(loaded, trimesh.Scene):
        mesh = trimesh.util.concatenate(loaded.dump())
    else:
        mesh = loaded

    original_faces = len(mesh.faces)
    original_verts = len(mesh.vertices)
    print(f"[retopo] Input: {original_verts} vertices, {original_faces} faces")

    if original_faces <= target_tris:
        print(f"[retopo] Already under target ({original_faces} <= {target_tris}), skipping decimation")
        mesh.export(output_path)
        return {
            'original_faces': original_faces,
            'original_verts': original_verts,
            'final_faces': original_faces,
            'final_verts': original_verts,
            'reduction_pct': 0.0,
        }

    # Decimate using trimesh's built-in quadric decimation
    # This uses fast-simplification under the hood (Quadric Edge Collapse)
    print(f"[retopo] Decimating {original_faces} -> {target_tris} faces...")

    decimated = mesh.simplify_quadric_decimation(face_count=target_tris)

    final_faces = len(decimated.faces)
    final_verts = len(decimated.vertices)
    print(f"[retopo] Output: {final_verts} vertices, {final_faces} faces")
    reduction = round((1 - final_faces / max(original_faces, 1)) * 100, 1)
    print(f"[retopo] Reduction: {original_faces} -> {final_faces} ({reduction}%)")

    # Save
    decimated.export(output_path)
    print(f"[retopo] Saved to {output_path}")

    return {
        'original_faces': original_faces,
        'original_verts': original_verts,
        'final_faces': final_faces,
        'final_verts': final_verts,
        'reduction_pct': reduction,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Retopologize mesh for Roblox')
    parser.add_argument('--input', required=True, help='Input mesh file (GLB/OBJ/PLY/STL)')
    parser.add_argument('--output', required=True, help='Output mesh file')
    parser.add_argument('--target-tris', type=int, default=4000,
                        help='Target triangle count (default: 4000)')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found")
        sys.exit(1)

    retopologize(args.input, args.output, args.target_tris)
