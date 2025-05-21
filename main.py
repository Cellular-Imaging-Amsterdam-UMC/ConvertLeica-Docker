from leica_converter import convert_leica
import sys
import argparse

parser = argparse.ArgumentParser(description='Convert Leica files')
parser.add_argument('--inputfile', required=True, help='Path to the input LIF/LOF/XLEF file')
parser.add_argument('--image_uuid', default='n/a')
parser.add_argument('--show_progress', action='store_true')
parser.add_argument('--outputfolder', default=None, required=True,)
parser.add_argument('--altoutputfolder', default=None)
parser.add_argument('--xy_check_value', type=int, default=3192)

args = parser.parse_args()

result = convert_leica(
    args.inputfile,
    args.image_uuid,
    args.show_progress,
    args.outputfolder,
    args.altoutputfolder,
    args.xy_check_value
)

if result and result != "[]":
    print(result)
    sys.exit(0)
else:
    print("Error")
    sys.exit(1)

