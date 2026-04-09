FROM ubuntu:22.04
LABEL org.opencontainers.image.source=https://github.com/RicardoZarate91/mesh-tools-runpod

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# System deps: Python, Blender, OpenGL libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev \
    blender \
    libgl1-mesa-glx libegl-mesa0 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Python packages
RUN pip3 install --no-cache-dir \
    runpod \
    trimesh \
    fast-simplification \
    numpy

WORKDIR /app

# Copy pipeline scripts
COPY handler.py .
COPY retopo.py .
COPY blender_decimate.py .
COPY blender_postprocess.py .
COPY blender_accessory.py .
COPY postprocess_clothing.py .

# Copy Roblox templates
COPY roblox-templates/ /opt/roblox-templates/

CMD ["python3", "handler.py"]
