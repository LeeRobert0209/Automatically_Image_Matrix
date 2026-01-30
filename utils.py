
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
    # Usually infer from extension, but if output_format is explicit, use it.
    
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
            
    # For PDF, we usually save as JPEG inside PDF for compression
    # For PNG, compression is lossless (optimization level), quality param ignored usually.
    
    quality = 95
    
    # PDF Logic
    if fmt == 'PDF':
        # PDF saving in PIL: image.save(f, "PDF", resolution=100.0, save_all=True...)
        # But for size constraint, we must compress the IMAGE first?
        # Actually PIL PDF saving might re-encode.
        # If we want small PDF, converting to 'RGB' and saving as PDF usually uses JPEG compression for RGB images.
        if image.mode != 'RGB':
             image = image.convert('RGB')
             
        if not max_kb or max_kb <= 0:
            image.save(output_path, "PDF", resolution=72.0, quality=quality)
            return
            
        # Strategy for PDF size limit:
        # It's hard to predict PDF overhead. But we can compress the image data conceptually.
        # Simple iterative quality reduction using temporary buffer or just quality param.
        # PIL's PDF writer respects 'quality' if the content is JPEG compressed.
        
        target_bytes = max_kb * 1024
        
        min_q = 10
        max_q = 95
        best_q = min_q
        
        # Binary Search for Quality
        while min_q <= max_q:
            mid_q = (min_q + max_q) // 2
            buf = io.BytesIO()
            image.save(buf, "PDF", resolution=72.0, quality=mid_q)
            size = buf.tell()
            
            if size <= target_bytes:
                best_q = mid_q
                min_q = mid_q + 1
            else:
                max_q = mid_q - 1
                
        image.save(output_path, "PDF", resolution=72.0, quality=best_q)
        return

    # PNG Logic (No quality param for size targeting really, use maximize optimization?)
    if fmt == 'PNG':
        # PNG is lossless. max_kb is hard to enforce without resizing.
        # We will ignore max_kb for PNG unless we decide to resize, but prompt implies quality/compression.
        # Let's just save optimized.
        image.save(output_path, "PNG", optimize=True)
        return

    # JPEG Logic (Standard)
    if fmt == 'JPEG':
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        if not max_kb or max_kb <= 0:
            image.save(output_path, "JPEG", quality=quality)
            return

        target_bytes = max_kb * 1024
        
        # Try different qualities
        # Fast recursive check
        
        # Check current quality=95
        buf = io.BytesIO()
        image.save(buf, "JPEG", quality=quality)
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
            image.save(buf, "JPEG", quality=mid_q)
            if buf.tell() <= target_bytes:
                best_q = mid_q
                min_q = mid_q + 1
            else:
                max_q = mid_q - 1
        
        image.save(output_path, "JPEG", quality=best_q)
