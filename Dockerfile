# Dockerfile for ConvertLeica-Docker
# Base image with Python 3.12
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system libvips (for vips support in Python)
RUN apt-get update && apt-get install -y libvips-dev && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app

# Create and activate virtual environment, install dependencies
RUN python -m venv /opt/venv \
    && . /opt/venv/bin/activate \
    && pip install --upgrade pip \
    && pip install -r requirements.txt

# Ensure venv is used for all future commands
ENV PATH="/opt/venv/bin:$PATH"

# Expose convert_leica as a CLI
ENTRYPOINT ["python", "main.py"]

# docker build -t convertleica .   

# WSL:
# docker run --rm -v "/mnt/c/data":/data -v "/mnt/c/data":/out convertleica --inputfile /data/RGB-Small.lif --image_uuid 710afbc4-24d7-11f0-bebf-80e82ce1e716 --outputfolder "/data/.processed" --altoutputfolder "/out" --show_progress
# docker run --rm -v "/mnt/c/data/xlef":/data -v "/mnt/c/data":/out convertleica --inputfile /data/Test-3-4-Channels.xlef --image_uuid 787dd736-c4c9-11ee-be7a-80e82ce1e716 --outputfolder "/data/.processed" --altoutputfolder "/out" --show_progress
# docker run --rm -v "/mnt/e/data":/data -v "/mnt/u/data":/out convertleica --inputfile /data/100T-21-P-NegOverlapTilescan.lif --image_uuid 8b48019d-6bf8-11ee-be69-80e82ce1e716 --outputfolder "/data/.processed" --altoutputfolder "/out" --show_progress
