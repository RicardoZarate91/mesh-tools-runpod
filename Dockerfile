FROM python:3.10-slim

# Install system deps: blender + build essentials for pymeshlab
RUN apt-get update && apt-get install -y --no-install-recommends \
    blender \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip install --no-cache-dir \
    runpod \
    pymeshlab \
    trimesh \
    numpy

# Set up working directory
WORKDIR /app

# Copy pipeline scripts
COPY handler.py .
COPY retopo.py .
COPY blender_postprocess.py .
COPY postprocess_clothing.py .

# Copy Roblox templates
COPY roblox-templates/ /opt/roblox-templates/

CMD ["python3", "handler.py"]
