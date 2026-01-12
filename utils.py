import os
import io
from PIL import Image

def save_compressed_image(image, output_path, max_kb=None):
    """
    Saves an image to the output_path, attempting to keep the file size under max_kb.
    
    Args:
        image (PIL.Image): The image to save.
        output_path (str): The full path to save the image to.
        max_kb (int, optional): The maximum file size in Kilobytes. If None or 0, no limit.
    """
    # Default quality
    quality = 95
    
    if not max_kb or max_kb <= 0:
        image.save(output_path, quality=quality)
        return

    target_bytes = max_kb * 1024
    
    # Try different qualities to find one that fits
    # Simple binary search or iterative approach
    # We will use an iterative approach for simplicity and safety
    
    # First check if 95 fits
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='JPEG', quality=quality)
    size = img_byte_arr.tell()
    
    if size <= target_bytes:
        with open(output_path, "wb") as f:
            f.write(img_byte_arr.getvalue())
        return

    # If 95 doesn't fit, try to reduce quality
    # We'll go from 90 down to 10 in steps of 5, then binary search?
    # Let's do a simple loop for robustness.
    
    min_quality = 5
    max_quality = 90
    best_quality = min_quality
    
    # Binary search for the highest quality that fits
    while min_quality <= max_quality:
        mid_quality = (min_quality + max_quality) // 2
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='JPEG', quality=mid_quality)
        size = img_byte_arr.tell()
        
        if size <= target_bytes:
            best_quality = mid_quality
            min_quality = mid_quality + 1 # Try higher
        else:
            max_quality = mid_quality - 1 # Need lower
            
    # Save with the best quality found
    # Note: If even quality=5 is too big, we just save at 5 (or logic to resize could be added here)
    image.save(output_path, quality=best_quality)
