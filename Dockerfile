# Dockerfile for ConvertLeica-Docker
# Base image with Python 3.12
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system libvips (for vips support in Python)
RUN apt-get update && apt-get install -y libvips-dev && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY requirements.txt /app/
COPY main.py leica_converter.py ci_leica_converters_helpers.py ci_leica_converters_single_lif.py ci_leica_converters_ometiff.py ci_leica_converters_ometiff_rgb.py ReadLeicaLIF.py ReadLeicaLOF.py ReadLeicaXLEF.py ParseLeicaImageXML.py /app/

# Create and activate virtual environment, install dependencies
RUN python -m venv /opt/venv \
    && . /opt/venv/bin/activate \
    && pip install --upgrade pip \
    && pip install -r requirements.txt

# Ensure venv is used for all future commands
ENV PATH="/opt/venv/bin:$PATH"

# Expose convert_leica as a CLI
ENTRYPOINT ["python", "main.py"]

# docker build -t convertleica-docker .   

# WSL Example usage:

# sudo mkdir -p /mnt/data
# sudo mount -t drvfs L:/Archief/active/cellular_imaging/OMERO_test/ValidateDocker /mnt/data

# docker run --rm -v "/mnt/data":/data -v "/mnt/data/.processed":/out -v "/mnt/data/out":/outalt convertleica-docker --inputfile /data/RGB.lif --image_uuid 710afbc4-24d7-11f0-bebf-80e82ce1e716 --outputfolder "/out" --altoutputfolder "/outalt" --show_progress
