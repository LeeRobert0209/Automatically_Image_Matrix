
import os
import io
from PIL import Image

def save_compressed_image(image, output_path, max_kb=None, output_format=None):
    """
    Saves an image to the output_path, attempting to keep the file size under max_kb.
    
    Args:
        image (PIL.Image): The image to save.
        output_path (str): The full path to save the image to.
        max_kb (int, optional): The maximum file size in Kilobytes. If None or 0, no limit.
        output_format (str, optional): 'JPEG', 'PNG', 'PDF' etc.
    """
    # 1. Determine Format if not given
    ext = os.path.splitext(output_path)[1].lower()
    if output_format:
        fmt = output_format.upper()
    else:
        if ext in ['.jpg', '.jpeg']:
            fmt = 'JPEG'
        elif ext == '.png':
            fmt = 'PNG'
        elif ext == '.pdf':
            fmt = 'PDF'
        else:
            fmt = 'JPEG' # Default
            
    # Common settings
    quality = 95
    dpi = image.info.get('dpi') # Preserve DPI
    
    # PDF Logic
    if fmt == 'PDF':
        if image.mode != 'RGB':
             image = image.convert('RGB')
        
        # Determine resolution for PDF (default to 72 if not present, or use image's DPI)
        resolution = 72.0
        if dpi:
            # dpi can be a tuple (x, y)
            resolution = float(dpi[0]) if isinstance(dpi, tuple) else float(dpi)

        if not max_kb or max_kb <= 0:
            image.save(output_path, "PDF", resolution=resolution, quality=quality)
            return
            
        target_bytes = max_kb * 1024
        
        min_q = 10
        max_q = 95
        best_q = min_q
        
        # Binary Search for Quality
        while min_q <= max_q:
            mid_q = (min_q + max_q) // 2
            buf = io.BytesIO()
            image.save(buf, "PDF", resolution=resolution, quality=mid_q)
            size = buf.tell()
            
            if size <= target_bytes:
                best_q = mid_q
                min_q = mid_q + 1
            else:
                max_q = mid_q - 1
                
        image.save(output_path, "PDF", resolution=resolution, quality=best_q)
        return

    # PNG Logic (Lossless, ignore max_kb usually)
    if fmt == 'PNG':
        if dpi:
            image.save(output_path, "PNG", optimize=True, dpi=dpi)
        else:
            image.save(output_path, "PNG", optimize=True)
        return

    # JPEG Logic (Standard)
    if fmt == 'JPEG':
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        # Use subsampling=0 (4:4:4) to prevent color bleed/blurriness
        save_kwargs = {'quality': quality, 'subsampling': 0}
        if dpi:
            save_kwargs['dpi'] = dpi

        if not max_kb or max_kb <= 0:
            image.save(output_path, "JPEG", **save_kwargs)
            return

        target_bytes = max_kb * 1024
        
        # Check current quality=95
        buf = io.BytesIO()
        image.save(buf, "JPEG", **save_kwargs)
        if buf.tell() <= target_bytes:
            with open(output_path, "wb") as f:
                f.write(buf.getvalue())
            return
            
        # Binary search
        min_q = 5
        max_q = 90
        best_q = min_q
        
        while min_q <= max_q:
            mid_q = (min_q + max_q) // 2
            buf = io.BytesIO()
            # Update quality in kwargs
            # NOTE: We maintain subsampling=0 and dpi for consistency
            current_kwargs = save_kwargs.copy()
            current_kwargs['quality'] = mid_q
            
            image.save(buf, "JPEG", **current_kwargs)
            
            if buf.tell() <= target_bytes:
                best_q = mid_q
                min_q = mid_q + 1
            else:
                max_q = mid_q - 1
        
        final_kwargs = save_kwargs.copy()
        final_kwargs['quality'] = best_q
        image.save(output_path, "JPEG", **final_kwargs)
