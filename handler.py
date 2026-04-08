#!/usr/bin/env python3
"""
handler.py -- RunPod serverless handler for mesh post-processing.

CPU-only endpoint. No AI models, just mesh tools:
  - "remesh":    Retopologize a GLB to a target tri count (PyMeshLab)
  - "roblox_lc": Full Roblox Layered Clothing pipeline (retopo + Blender fit/cage/rig)

Input:
  {
    "input": {
      "glb": "<base64-encoded GLB>",
      "mode": "remesh" | "roblox_lc",
      "target_tris": 4000,
      "clothing_type": "shirt"   // roblox_lc only
    }
  }
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request

import runpod
import trimesh

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def decode_glb(b64_string, dest_path):
    """Decode base64 GLB and write to dest_path."""
    raw = base64.b64decode(b64_string)
    with open(dest_path, "wb") as f:
        f.write(raw)
    size_mb = len(raw) / (1024 * 1024)
    print(f"[handler] Decoded GLB: {size_mb:.2f} MB -> {dest_path}")
    return len(raw)


def encode_file(filepath):
    """Read a file and return its base64 encoding."""
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def file_size_mb(filepath):
    """Return file size in MB, or 0 if missing."""
    if os.path.exists(filepath):
        return round(os.path.getsize(filepath) / (1024 * 1024), 3)
    return 0


# ---------------------------------------------------------------------------
# Mode: remesh
# ---------------------------------------------------------------------------

def handle_remesh(input_glb_path, target_tris, work_dir):
    """
    Retopologize a GLB to target_tris using PyMeshLab.
    Returns dict with result GLB (base64) and metadata.
    """
    t0 = time.time()

    # Retopologize directly (trimesh handles GLB natively)
    sys.path.insert(0, os.path.dirname(__file__))
    from retopo import retopologize

    output_glb = os.path.join(work_dir, "output.glb")
    stats = retopologize(input_glb_path, output_glb, target_tris)

    elapsed = time.time() - t0

    return {
        "glb": encode_file(output_glb),
        "glb_size_mb": file_size_mb(output_glb),
        "original_faces": original_faces,
        "original_verts": original_verts,
        "final_faces": stats["final_faces"],
        "final_verts": stats["final_verts"],
        "reduction_pct": stats["reduction_pct"],
        "elapsed_sec": round(elapsed, 2),
    }


# ---------------------------------------------------------------------------
# Mode: roblox_lc
# ---------------------------------------------------------------------------

def handle_roblox_lc(input_glb_path, target_tris, clothing_type, work_dir):
    """
    Full Roblox Layered Clothing pipeline:
      1. Retopology (PyMeshLab)
      2. Blender: fit to mannequin, cage, rig, export FBX
    Returns dict with GLB, FBX, mannequin preview GLB (all base64) + metadata.
    """
    t0 = time.time()

    output_dir = os.path.join(work_dir, "roblox_output")
    os.makedirs(output_dir, exist_ok=True)

    # Run the full pipeline via postprocess_clothing.py
    script = os.path.join(os.path.dirname(__file__), "postprocess_clothing.py")
    cmd = [
        sys.executable, script,
        "--input", input_glb_path,
        "--output-dir", output_dir,
        "--clothing-type", clothing_type,
        "--target-tris", str(target_tris),
    ]
    print(f"[handler] Running: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    # Log output
    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            print(f"  {line}")
    if result.returncode != 0:
        stderr_tail = result.stderr[-2000:] if result.stderr else "(no stderr)"
        raise RuntimeError(
            f"postprocess_clothing.py failed (exit {result.returncode}):\n{stderr_tail}"
        )

    elapsed = time.time() - t0

    # Read metadata
    meta_path = os.path.join(output_dir, "metadata.json")
    metadata = {}
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            metadata = json.load(f)

    # Encode output files
    preview_glb = os.path.join(output_dir, "clothing_preview.glb")
    roblox_fbx = os.path.join(output_dir, "clothing_roblox.fbx")
    mannequin_glb = os.path.join(output_dir, "clothing_on_mannequin.glb")

    response = {
        "elapsed_sec": round(elapsed, 2),
        "metadata": metadata,
    }

    if os.path.exists(preview_glb):
        response["glb"] = encode_file(preview_glb)
        response["glb_size_mb"] = file_size_mb(preview_glb)

    if os.path.exists(roblox_fbx):
        response["fbx"] = encode_file(roblox_fbx)
        response["fbx_size_mb"] = file_size_mb(roblox_fbx)

    if os.path.exists(mannequin_glb):
        response["mannequin_glb"] = encode_file(mannequin_glb)
        response["mannequin_glb_size_mb"] = file_size_mb(mannequin_glb)

    return response


# ---------------------------------------------------------------------------
# RunPod handler
# ---------------------------------------------------------------------------

def handler(job):
    """RunPod serverless handler entry point."""
    job_input = job["input"]
    job_id = job.get("id", "unknown")

    mode = job_input.get("mode", "remesh")
    target_tris = int(job_input.get("target_tris", 4000))
    clothing_type = job_input.get("clothing_type", "shirt")
    glb_b64 = job_input.get("glb")
    glb_url = job_input.get("glb_url")

    print(f"[handler] Job {job_id} | mode={mode} | target_tris={target_tris} | clothing_type={clothing_type}")

    if not glb_b64 and not glb_url:
        return {"error": "Missing required field: input.glb (base64) or input.glb_url (URL)"}

    if mode not in ("remesh", "roblox_lc"):
        return {"error": f"Unknown mode '{mode}'. Must be 'remesh' or 'roblox_lc'."}

    with tempfile.TemporaryDirectory(prefix="mesh_tools_") as work_dir:
        try:
            # Get input GLB (from base64 or URL)
            input_glb = os.path.join(work_dir, "input.glb")
            if glb_url:
                print(f"[handler] Downloading GLB from URL: {glb_url[:80]}...")
                urllib.request.urlretrieve(glb_url, input_glb)
                print(f"[handler] Downloaded: {file_size_mb(input_glb)} MB")
            else:
                decode_glb(glb_b64, input_glb)

            if mode == "remesh":
                result = handle_remesh(input_glb, target_tris, work_dir)
            else:
                result = handle_roblox_lc(input_glb, target_tris, clothing_type, work_dir)

            result["mode"] = mode
            result["status"] = "success"
            return result

        except Exception as e:
            traceback.print_exc()
            return {
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            }


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("[handler] Starting mesh-tools-runpod serverless worker...")
    runpod.serverless.start({"handler": handler})
