import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ci_leica_converters_ometiff_rgb import convert_leica_rgb_to_ometiff  # Updated function name
 
lif_file_path='L:/Archief/active/cellular_imaging/OMERO_test/Leica-XLEF/2023_11_09_15_40_20--MAPS Sample1-4/MAPS Sample1-4.xlef'
image_uuid = "0738d4f1-7f11-11ee-aa38-b49691ed54d9" # 13437 x 24038 tilescan RGB

# lif_file_path='L:/Archief/active/cellular_imaging/OMERO_test/Leica-XLEF/2023_11_09_15_40_20--MAPS Sample1-4/MAPS Sample1-4.xlef'
# image_uuid = "06fc3fbf-94cd-456d-eab0-21c49c8e3d90" # large tilescan RGB

# lif_file_path='L:/Archief/active/cellular_imaging/OMERO_test/ConvertTest/TileScan_losseTiles.lif'
# image_uuid = "341662b2-2324-11ea-8af9-484d7eeb8d5c" # Losse Files tilescan RGB

# lif_file_path='L:/Archief/active/cellular_imaging/OMERO_test/Leica-LIF/RGB-Small.lif'
# image_uuid = "710afbc4-24d7-11f0-bebf-80e82ce1e716" # tilescan RGB small

fname = convert_leica_rgb_to_ometiff(lif_file_path, image_uuid=image_uuid, outputfolder='E:/cc' , altoutputfolder='U:/cc') # Use updated function name
print(fname)


# docker run --rm -v "L:\Archief\active\cellular_imaging\OMERO_test\Leica-LIF\":/data convertleica RGB-Small.lif --show_progress