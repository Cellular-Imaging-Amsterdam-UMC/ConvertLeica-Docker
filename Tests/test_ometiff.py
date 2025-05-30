
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ci_leica_converters_ometiff import convert_leica_to_ometiff

# lif_file_path = 'L:/Archief/active/cellular_imaging/OMERO_test/Leica-LIF/Swiss Rolls GM1748 LEX277AD.lif'  # Replace with your LIF file path
# image_uuid = "ad7b9384-0466-11e9-8a36-8cec4b8a9866"  # 8417 x 15015 tilescan

lif_file_path = 'L:/Archief/active/cellular_imaging/OMERO_test/Leica-LIF/Swiss Rolls GM1748 LEX277AD.lif'  # Replace with your LIF file path
image_uuid = "f9db17a2-039c-11e9-8eec-28107b9f42d1"  # 8417 x 15015 losse tiles tilescan

# lif_file_path = 'L:/Archief/active/cellular_imaging/OMERO_test/Leica-LIF/MPO_30h_dosis8_left.lif'  # Replace with your LIF file path
# image_uuid =  "f7397261-100d-41f3-17a2-490da985ed76"  # 3D

# lif_file_path = 'L:/Archief/active/cellular_imaging/OMERO_test/Leica-LOF/Slide 3-Mosaic001_ICC_Merged.lof'  # Replace with your LIF file path
# image_uuid='n/a'

# lif_file_path = 'L:/Archief/active/cellular_imaging/OMERO_test/Leica-LIF/WF-2D.lif'  # Replace with your LIF file path
# image_uuid='75c3b22a-2408-11f0-bebf-80e82ce1e716'

# lif_file_path = 'L:/Archief/active/cellular_imaging/OMERO_test/Leica-LIF/clone_171.lif'  # Replace with your LIF file path
# image_uuid='8e51b99d-c40e-4703-92e0-0c6df29b4156'
 
# lif_file_path = 'L:/Archief/active/cellular_imaging/OMERO_test/Leica-LOF/4Channels.lof'  # Replace with your LIF file path
# image_uuid='n/a'

# RGB XLEF file
# lif_file_path='L:/Archief/active/cellular_imaging/OMERO_test/Leica-XLEF/2023_11_09_15_40_20--MAPS Sample1-4/MAPS Sample1-4.xlef'
# image_uuid = "0738d4f1-7f11-11ee-aa38-b49691ed54d9" # 13437 x 24038 tilescan RGB

# lif_file_path = 'L:/Archief/active/cellular_imaging/OMERO_test/Leica-LIF/test-lasx-full.lif'  # Replace with your LIF file path
# image_uuid = "b205840d-f11f-11e1-b45a-0015774387e6"  # 3D

# lif_file_path = 'L:/Archief/active/cellular_imaging/OMERO_test/Leica-LIF/Peroxisomes.lif'  # Replace with your LIF file path
# image_uuid = "2189de82-8ebf-11e6-b044-5065f31b8ec5"  # 2D Time

# lif_file_path = 'L:/Archief/active/cellular_imaging/OMERO_test/Leica-LOF/100T-21-P-NegOverlapTilescan.lof'  # Replace with your LIF file path
# image_uuid='n/a'


# lif_file_path='L:/Archief/active/cellular_imaging/OMERO_test/Leica-XLEF/2025_05_01_14_00_03--LongTime/Project002.xlef'
# image_uuid = "e778565c-2683-11f0-858b-c8d9d2330798" 

# lif_file_path='L:/Archief/active/cellular_imaging/OMERO_test/Leica-XLEF/Test-3-4-Channels.xlef/Project002.xlef'
# image_uuid = "e778565c-2683-11f0-858b-c8d9d2330798" 


fname = convert_leica_to_ometiff(lif_file_path, image_uuid=image_uuid, outputfolder='E:/cc' , altoutputfolder='U:/cc')
print(fname)
