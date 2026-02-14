import os
import fitz  # PyMuPDF
from PIL import Image
from psd_tools import PSDImage
import win32com.client
import pythoncom

def convert_pdf_to_images(file_path, output_dir, fmt='jpg'):
    """
    Convert PDF pages to images using PyMuPDF.
    """
    results = []
    try:
        doc = fitz.open(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # Create folder for this file
        file_out_dir = os.path.join(output_dir, base_name)
        if not os.path.exists(file_out_dir):
            os.makedirs(file_out_dir)

        for i in range(len(doc)):
            page = doc.load_page(i)
            # Use 2.0 zoom for better quality (approx 144 dpi) -> or 300/72 * 1 = 4.16 for 300 dpi
            # Let's use zoom=2 for balance (approx 150 dpi screen quality)
            # User wants "High Quality", let's give them 300 DPI equivalent (~4x)
            zoom = 4.0 
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            # Save
            ext = f".{fmt}"
            out_name = f"{base_name}_page{i+1:03d}{ext}"
            out_path = os.path.join(file_out_dir, out_name)
            
            # PyMuPDF save
            if fmt == 'jpg':
                pix.save(out_path) # saves as png/jpg based on extension? 
                # pix.save handles basics. For jpg specific quality controls, better use PIL?
                # fitz pixmap can save directly.
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img.save(out_path, quality=95, dpi=(300, 300))
            else:
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img.save(out_path, dpi=(300, 300))
                
            results.append(out_path)
            
        return True, f"Converted {len(results)} pages."
    except Exception as e:
        return False, str(e)

def convert_psd_to_images(file_path, output_dir, fmt='jpg'):
    """
    Convert PSD to image using psd-tools.
    """
    try:
        psd = PSDImage.open(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # Output directly to dir, or make subfolder? 
        # For single image conversion, maybe just file? 
        # But consistency: let's make a folder if it's a batch tool?
        # Actually PSD is usually one image (composite).
        
        ext = f".{fmt}"
        out_name = f"{base_name}{ext}"
        out_path = os.path.join(output_dir, out_name)
        
        # Get composite image
        image = psd.composite()
        if image:
            # Preserve DPI? psd-tools might have it?
            # Manually saving
            if fmt == 'jpg':
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                image.save(out_path, quality=95)
            else:
                image.save(out_path)
            return True, f"Converted PSD to {out_name}"
        else:
             return False, "No composite image found in PSD."
    except Exception as e:
        return False, str(e)

def convert_ppt_to_images(file_path, output_dir, fmt='jpg'):
    """
    Convert PPT/PPTX to images using Windows COM interface.
    """
    try:
        # COM initialization for threads
        pythoncom.CoInitialize()
        
        powerpoint = win32com.client.Dispatch("PowerPoint.Application")
        # Ensure it doesn't pop up intrusively, though it needs to run
        # powerpoint.Visible = True # PowerPoint often requires visibility to export
        
        abs_path = os.path.abspath(file_path)
        presentation = powerpoint.Presentations.Open(abs_path, WithWindow=False)
        
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        file_out_dir = os.path.join(output_dir, base_name)
        if not os.path.exists(file_out_dir):
            os.makedirs(file_out_dir)
            
        # Export
        # ppSaveAsJPG = 17, ppSaveAsPNG = 18
        save_format = 17 if fmt == 'jpg' else 18
        
        # This exports ALL slides into the folder
        presentation.SaveAs(file_out_dir, save_format)
        presentation.Close()
        
        # Check results
        files = os.listdir(file_out_dir)
        count = len([f for f in files if f.lower().endswith(f".{fmt}")])
        
        return True, f"Converted {count} slides."
        
    except Exception as e:
        return False, f"PPT Error (Requires MS Office): {e}"
    finally:
        pythoncom.CoUninitialize()
