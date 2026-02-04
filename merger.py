
from PIL import Image
import os
import io

# Disable the DecompressionBombError for large images
Image.MAX_IMAGE_PIXELS = None

def get_compressed_image(image, max_kb):
    """
    Returns a copy of the image compressed to be under max_kb.
    Returns the original image (converted to RGB) if max_kb is not valid or compression fails.
    """
    if image.mode != 'RGB':
        image = image.convert('RGB')
        
    if not max_kb or max_kb <= 0:
        return image
        
    target_bytes = max_kb * 1024
    
    # Binary search for quality
    min_q = 10
    max_q = 95
    best_q = min_q
    
    # Quick check at 95
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=95)
    if buf.tell() <= target_bytes:
        return image # already small enough
        
    best_img_bytes = None
    
    while min_q <= max_q:
        mid_q = (min_q + max_q) // 2
        buf = io.BytesIO()
        image.save(buf, "JPEG", quality=mid_q)
        size = buf.tell()
        
        if size <= target_bytes:
            best_q = mid_q
            best_img_bytes = buf.getvalue()
            min_q = mid_q + 1
        else:
            max_q = mid_q - 1
            
    if best_img_bytes:
        return Image.open(io.BytesIO(best_img_bytes))
    else:
        # If even at lowest quality it's too big, just return lowest quality version
        buf = io.BytesIO()
        image.save(buf, "JPEG", quality=10)
        return Image.open(io.BytesIO(buf.getvalue()))


def merge_images_to_pdf(image_paths, output_path, max_kb_per_page=None):
    """
    Merges multiple images into a single PDF file.
    """
    if not image_paths:
        return False, "No images selected."
        
    try:
        images_to_save = []
        
        for path in image_paths:
            try:
                img = Image.open(path)
                
                # Check for multiple frames/pages (GIF, PDF, TIFF)
                n_frames = getattr(img, 'n_frames', 1)
                
                for i in range(n_frames):
                    img.seek(i)
                    # Convert to RGB immediately to handle various modes and ensure copy
                    frame = img.convert('RGB')
                    
                    # Compress/Process
                    processed_img = get_compressed_image(frame, max_kb_per_page)
                    images_to_save.append(processed_img)

            except Exception as e:
                print(f"Warning: Failed to load {path}: {e}")
                
        if not images_to_save:
            return False, "No valid images to merge."
            
        # Save to PDF
        # The first image is the 'base', others are appended
        base_image = images_to_save[0]
        other_images = images_to_save[1:]
        
        # We assume save using default PDF quality (which might be re-compressed). 
        # But since we fed in compressed objects, it should be okay-ish.
        # Alternatively, we can pass quality=... here too? 
        # PIL PDF driver uses 'quality' arg if available.
        
        base_image.save(output_path, "PDF", resolution=100.0, save_all=True, append_images=other_images, quality=95)
        
        return True, f"Successfully merged {len(images_to_save)} images into {os.path.basename(output_path)}"
        
    except Exception as e:
        return False, f"Error merging PDF: {e}"
