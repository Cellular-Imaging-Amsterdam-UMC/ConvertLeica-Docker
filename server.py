import os
import json
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from ci_leica_converters_helpers import read_leica_file,get_image_metadata,get_image_metadata_LOF
from CreatePreview import create_preview_base64_image
from leica_converter import convert_leica
import threading
import uuid
import sys
import traceback

class SSEStream:
    def __init__(self, wfile):
        self.wfile = wfile
        self.line_buffer = ""
    def write(self, chunk):
        if not self.wfile:
            return
        self.line_buffer += chunk
        while '\n' in self.line_buffer:
            line, self.line_buffer = self.line_buffer.split('\n', 1)
            if line.strip():
                msg = json.dumps({"type":"progress","message":line})
                sse = f"data: {msg}\n\n"
                try:
                    self.wfile.write(sse.encode())
                    self.wfile.flush()
                except:
                    self.wfile = None
    def flush(self):
        if self.line_buffer.strip() and self.wfile:
            msg = json.dumps({"type":"progress","message":self.line_buffer.strip()})
            sse = f"data: {msg}\n\n"
            try:
                self.wfile.write(sse.encode())
                self.wfile.flush()
            except:
                self.wfile = None
        self.line_buffer = ""

ROOT_DIR = "L:/Archief/active/cellular_imaging/OMERO_test"  # change as needed

class MyHTTPRequestHandler(SimpleHTTPRequestHandler):

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            if parsed.path == "/api/list":
                self.handle_list(parsed.query)
            elif parsed.path == "/api/browse":
                self.handle_browse(parsed.query)
            elif parsed.path == "/api/preview":
                self.handle_preview(parsed.query)
            else:
                self.send_response(404)
                self.end_headers()
            return
        # Else serve files as usual.
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/preview":
            self.handle_preview()
        elif parsed.path == "/api/lof_metadata":
            self.handle_lof_metadata()
        elif parsed.path == "/api/convert_leica":
            self.handle_convert_leica()
        elif parsed.path == "/api/check_progress":
            self.handle_check_progress()
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def handle_list(self, query):
        params = urllib.parse.parse_qs(query)
        # If no "dir" provided, use the ROOT_DIR.
        directory = params.get("dir", [ROOT_DIR])[0]
        directory = os.path.normpath(directory)
        folder_uuid = params.get("folder_uuid", [None])[0]  # Get folder_uuid from query
        
        response = {"items": []}
        try:
            ext = os.path.splitext(directory)[1].lower()
            if not os.path.isdir(directory) and ext in (".lif", ".xlef"):
                if folder_uuid:
                    folder_metadata = read_leica_file(directory, folder_uuid=folder_uuid)  # Pass folder_uuid
                else:
                    folder_metadata = read_leica_file(directory)
                try:
                    parsed_dict = json.loads(folder_metadata)
                    if "children" in parsed_dict:
                        for child in parsed_dict["children"]:
                            name = child.get("name", "").lower()
                            if ("_environmentalgraph" in name or 
                                name.endswith(".lifext") or 
                                name in ["iomanagerconfiguation", "iomanagerconfiguration"]):
                                continue
                            if "path" not in child:
                                child["path"] = directory
                            response["items"].append(child)
                    else:
                        response["items"] = [parsed_dict]
                    response["folder_metadata"] = folder_metadata  # Pass folder_metadata to client
                except json.JSONDecodeError as e:
                    print(f"JSONDecodeError: {e}")
                    response = folder_metadata
            else:
                # List directory items.
                all_items = os.listdir(directory)
                # If at least one .xlef file exists, filter to only .xlef files.
                if any(os.path.splitext(n)[1].lower() == ".xlef" for n in all_items):
                    items_to_list = [n for n in all_items if os.path.splitext(n)[1].lower() == ".xlef"]
                else:
                    items_to_list = all_items

                for name in items_to_list:
                    lowname = name.lower()
                    if ("metadata" in lowname or "_pmd_" in lowname or "_histo" in lowname or
                        "_environmetalgraph" in lowname or lowname.endswith(".lifext") or
                        lowname in ["iomanagerconfiguation", "iomanagerconfiguration"]):
                        continue
                    abs_path = os.path.join(directory, name)
                    if os.path.isdir(abs_path) or os.path.splitext(name)[1].lower() in (".lif", ".xlef"):
                        item_type = "Folder"
                    else:
                        item_type = "File"
                    response["items"].append({
                        "name": name,
                        "path": abs_path,
                        "type": item_type
                    })
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_browse(self, query):
        params = urllib.parse.parse_qs(query)
        filePath = params.get("filePath", [None])[0]

        if not filePath:
            self.send_error(400, "Missing filePath parameter")
            return

        try:
            result = read_leica_file(filePath)
            try:
                result_dict = json.loads(result)
                out = json.dumps(result_dict)
                content_type = "application/json"
            except json.JSONDecodeError as e:
                print(f"JSONDecodeError: {e}")
                out = result
                content_type = "text/plain"

            self.send_response(200)
            self.send_header("Content-type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(out.encode("utf-8"))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_lof_metadata(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        try:
            data = json.loads(post_data.decode('utf-8'))
            filePath = data.get("filePath")

            if not filePath:
                self.send_error(400, "Missing filePath parameter")
                return

            try:
                metadata = read_leica_file(filePath)
                metadata = json.loads(metadata) # Parse the metadata string into a JSON object
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(metadata).encode("utf-8")) # Send the JSON object
            except Exception as e:
                self.send_error(500, str(e))

        except Exception as e:
            self.send_error(500, str(e))

    def handle_preview(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        try:
            data = json.loads(post_data.decode('utf-8'))
            filePath = data.get("filePath")
            image_uuid = data.get("image_uuid")
            folder_metadata = data.get("folder_metadata")
            preview_height = data.get("preview_height", 256)  # Default to 256 if not provided

            ext = os.path.splitext(filePath)[1].lower()
            if ext == ".lof":
                image_metadata = read_leica_file(filePath)
            elif ext == ".xlef": # If xlef file, get image metadata("save_child_name") from folder_metadata
                image_metadata_f = json.loads(get_image_metadata(folder_metadata, image_uuid))
                image_metadata = json.loads(get_image_metadata_LOF(folder_metadata, image_uuid))
                if "save_child_name" in image_metadata_f:
                    image_metadata["save_child_name"] = image_metadata_f["save_child_name"]
                image_metadata = json.dumps(image_metadata)  # Convert back to JSON string
            else:
                image_metadata = get_image_metadata(folder_metadata, image_uuid)
            src = create_preview_base64_image(image_metadata, preview_height=preview_height, use_memmap=True)

            # Return both preview src and image metadata
            response = {"src": src, "metadata": image_metadata}
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
        except Exception as e:
            self.send_error(500, str(e))


    def handle_convert_leica(self):
        sse = None                               # initialize
        orig_stdout = sys.stdout
        content_length = int(self.headers['Content-Length'])
        post = self.rfile.read(content_length)

        try:
            data = json.loads(post.decode())
            inp = data.get("filePath")
            uuid_ = data.get("image_uuid")
            if not inp or not uuid_:
                self.send_response(400)
                self.send_header("Content-Type","application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success":False,"error":"Missing parameters"}).encode())
                return

            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.send_header("Cache-Control","no-cache")
            self.send_header("Connection","keep-alive")
            self.send_header("Access-Control-Allow-Origin","*")
            self.end_headers()

            sse = SSEStream(self.wfile)
            sys.stdout = sse

            # determine output folder
            outdir = os.path.join(os.path.dirname(inp), "_c")
            os.makedirs(outdir, exist_ok=True)

            # call converter
            result_json = convert_leica(
                inputfile=inp,
                image_uuid=uuid_,
                outputfolder=outdir,
                show_progress=True
            )
            sse.flush()

            try:
                result = json.loads(result_json)
            except:
                result = []
            payload = {"type":"result","payload":{"success":bool(result),"result":result}}
            if sse.wfile:
                self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
                self.wfile.flush()

        except Exception as e:
            if sse:
                sse.flush()
            err = {"type":"error","message":str(e)}
            if sse and sse.wfile:
                self.wfile.write(f"data: {json.dumps(err)}\n\n".encode())
                self.wfile.flush()
        finally:
            sys.stdout = orig_stdout
            if sse and sse.wfile:
                self.wfile.write(f"data: {json.dumps({'type':'end'})}\n\n".encode())
                self.wfile.flush()

    def handle_check_progress(self):
        """
        API endpoint to check the progress of a task.
        
        Accepts a POST request with a JSON body containing:
        - task_id: The UUID of the export task to check
        
        Returns a JSON response with:
        - success: Boolean indicating if the request was processed successfully
        - progress_info: Object containing current progress status, percentage, and messages
        """
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        try:
            data = json.loads(post_data.decode('utf-8'))
            task_id = data.get("task_id")
            
            if not task_id:
                response = {"success": False, "error": "Missing task_id parameter"}
                self.send_response(400)
            else:
                # Only check the LIF conversion progress dictionary
                from CreateSingleImageLIF import conversion_progress as lif_progress
                # Removed QPTIFF progress tracking
                # from CreateQPTIFF import conversion_progress as qptiff_progress
                
                # Only check lif_progress for the task_id
                if task_id in lif_progress:
                    progress_info = lif_progress[task_id]
                else:
                    progress_info = {"progress": 0, "status": "unknown", "message": "Task not found"}
                
                response = {"success": True, "progress_info": progress_info}
                self.send_response(200)
            
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
        except Exception as e:
            self.send_error(500, str(e))

def run(server_class=ThreadingHTTPServer, handler_class=MyHTTPRequestHandler, port=8000):
    server_address = ("", port)
    httpd = server_class(server_address, handler_class)
    print(f"Starting server on http://localhost:{port}")
    httpd.serve_forever()

if __name__ == "__main__":
    run()