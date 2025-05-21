import uuid
import xml.etree.ElementTree as ET
import os
import shutil
from ci_leica_converters_helpers import print_progress_bar, read_image_metadata

def convert_leica_to_singlelif(inputfile, image_uuid, outputfolder=None, show_progress=True, altoutputfolder=None):
    """
    Creates a LIF file from a single image within an existing LIF file,
    using the image's UUID to extract its metadata.

    Args:
        inputfile (str): Path to the original LIF file.
        image_uuid (str): UUID of the image to extract.
        outputfolder (str, optional): Full path to output folder. If None, same directory as the input file is used.
        show_progress (bool): Whether to show progress (default=True).
        altoutputfolder (str, optional): Optional alternative second output folder. Defaults to None.

    Returns:
        str: The filename of the created LIF file (without path), or None if an error occurred.
    """
    try:
        if show_progress:
            print_progress_bar(5.0, prefix='Creating Single LIF:', suffix='Reading metadata')

        metadata = read_image_metadata(inputfile, image_uuid)

        if show_progress:
            print_progress_bar(10.0, prefix='Creating Single LIF:', suffix='Processing metadata')

        xml_element = metadata.get('xmlElement')
        save_child_name = metadata.get('save_child_name')
        name = metadata.get('name')

        if xml_element:
            root = ET.fromstring(xml_element)
            for el in root.iter('Element'):
                if el.get('Name') == name:
                    el.set('Name', save_child_name)
            xml_element = ET.tostring(root, encoding='unicode')

        BlockID = metadata.get('BlockID')
        memory_size = metadata.get('MemorySize')
        image_data_path = inputfile
        image_data_position = metadata.get('Position')

        if outputfolder is None:
            outputfolder = os.path.dirname(inputfile)
        
        os.makedirs(outputfolder, exist_ok=True)
        
        if altoutputfolder is not None:
            os.makedirs(altoutputfolder, exist_ok=True)

        base_lif_filename = save_child_name + ".lif"
        lif_filepath = os.path.join(outputfolder, base_lif_filename)

        if show_progress:
            print_progress_bar(30.0, prefix='Creating Single LIF:', suffix='Creating LIF file header')

        outxml = '<LMSDataContainerHeader Version="2"><Element CopyOption="1" Name="_name_" UniqueID="_uuid_" Visibility="1"> <Data><Experiment IsSavedFlag="1" Path="_path_"/></Data><Memory MemoryBlockID="MemBlock_221" Size="0"/><Children>_element_</Children></Element></LMSDataContainerHeader>'
        outxml = outxml.replace('_name_', save_child_name)
        outxml = outxml.replace('_path_', lif_filepath) 
        outxml = outxml.replace('_uuid_', str(uuid.uuid4()))
        outxml = outxml.replace('_element_', xml_element)

        outxml = outxml.replace('\n', '')
        outxml = ' '.join(outxml.split())
        outxml = outxml.replace('</Data>', '</Data>\r\n')
        outxml = outxml.replace('</LMSDataContainerHeader>', '</LMSDataContainerHeader>\r\n')
        outxml16 = outxml.encode('utf-16')[2:]

        if show_progress:
            print_progress_bar(40.0, prefix='Creating Single LIF:', suffix='Writing LIF file structure')

        with open(lif_filepath, 'wb') as fid:
            fid.write(int(0x70).to_bytes(4, 'little'))
            fid.write(int(len(outxml16) + 1 + 4).to_bytes(4, 'little'))
            fid.write(int(0x2A).to_bytes(1, 'little'))
            fid.write(int(len(outxml16) // 2).to_bytes(4, 'little'))
            fid.write(outxml16)

            elementMemID = "MemBlock_221"
            msize = 0
            mdescription = f"{elementMemID}".encode('utf-16')[2:]        
            fid.write(int(0x70).to_bytes(4, 'little'))
            fid.write(int(len(mdescription) + 1 + 8 + 1 + 4).to_bytes(4, 'little'))
            fid.write(int(0x2A).to_bytes(1, 'little'))
            fid.write(int(msize).to_bytes(8, 'little'))
            fid.write(int(0x2A).to_bytes(1, 'little'))
            fid.write(int(len(mdescription) // 2).to_bytes(4, 'little'))
            fid.write(mdescription)

            elementMemID = BlockID
            msize = memory_size
            mdescription = f"{elementMemID}".encode('utf-16')[2:]        
            fid.write(int(0x70).to_bytes(4, 'little'))
            fid.write(int(len(mdescription) + 1 + 8 + 1 + 4).to_bytes(4, 'little'))
            fid.write(int(0x2A).to_bytes(1, 'little'))
            fid.write(int(msize).to_bytes(8, 'little'))
            fid.write(int(0x2A).to_bytes(1, 'little'))
            fid.write(int(len(mdescription) // 2).to_bytes(4, 'little'))
            fid.write(mdescription)

            if image_data_path and msize > 0:
                copy_memory_block_with_text_progress(image_data_path, fid, msize, image_data_position, show_progress)

        if show_progress:
            print_progress_bar(100.0, prefix='Creating Single LIF:', suffix='Complete', final_call=True)
        
        print(f"LIF file created: {lif_filepath}") 

        if altoutputfolder is not None:
            alt_out_path = os.path.join(altoutputfolder, base_lif_filename)
            shutil.copy2(lif_filepath, alt_out_path)
            print(f"LIF file also copied to: {alt_out_path}")

        return base_lif_filename 
        
    except ValueError as ve:
        print(f"\nError processing metadata for UUID {image_uuid}: {str(ve)}")
        return None
    except Exception as e:
        print(f"\nError creating LIF file: {str(e)}") 
        return None

def copy_memory_block(input_file, output_file, memory_size, offset):
    """
    Original function - Copies a memory block from an input file to an output file
    in chunks, starting from a specific offset.
    """
    block_size = 25600000
    num_full_blocks = memory_size // block_size
    final_block_size = memory_size % block_size

    with open(input_file, 'rb') as fid:
        fid.seek(offset, os.SEEK_SET)

        for i in range(num_full_blocks):
            memblock = fid.read(block_size)
            output_file.write(memblock)

        if final_block_size > 0:
            memblock = fid.read(final_block_size)
            output_file.write(memblock)

def copy_memory_block_with_text_progress(input_file, output_file, memory_size, offset, show_progress):
    """
    Console progress version - Copies a memory block from an input file to an output file
    in chunks, updating progress via console bar, spanning from 40% to 95% of the overall task.
    """
    block_size = 25600000
    num_full_blocks = memory_size // block_size
    final_block_size = memory_size % block_size

    total_blocks = num_full_blocks + (1 if final_block_size > 0 else 0)
    overall_progress_start = 40.0
    overall_progress_end = 95.0
    overall_progress_span = overall_progress_end - overall_progress_start

    if total_blocks == 0:
        if show_progress:
            print_progress_bar(overall_progress_end, prefix='Creating Single LIF:', suffix="No data to copy")
        return

    progress_increment = overall_progress_span / total_blocks

    with open(input_file, 'rb') as fid:
        fid.seek(offset, os.SEEK_SET)

        for i in range(num_full_blocks):
            memblock = fid.read(block_size)
            output_file.write(memblock)
            if show_progress:
                current_progress = min(overall_progress_end, overall_progress_start + ((i + 1) * progress_increment))
                print_progress_bar(current_progress, prefix='Creating Single LIF:', 
                                   suffix=f"Copying data: block {i + 1}/{total_blocks}")

        if final_block_size > 0:
            memblock = fid.read(final_block_size)
            output_file.write(memblock)
            if show_progress:
                print_progress_bar(overall_progress_end, prefix='Creating Single LIF:', suffix="Data copy complete")