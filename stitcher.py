
from PIL import Image
import os
import math

# Disable the DecompressionBombError for large images
Image.MAX_IMAGE_PIXELS = None

def _stitch_vertical(images, target_width=None):
    """
    Stitch images vertically.
    """
    if not images:
        return None

    # Calculate total dimensions
    max_width = max(img.width for img in images)
    total_height = sum(img.height for img in images)

    # Create new blank image
    stitched_img = Image.new('RGB', (max_width, total_height), (255, 255, 255))

    # Paste images
    current_y = 0
    for img in images:
        # Center the image horizontally
        x_offset = (max_width - img.width) // 2
        stitched_img.paste(img, (x_offset, current_y))
        current_y += img.height

    # Resize if target_width is specified
    if target_width:
        aspect_ratio = total_height / max_width
        new_height = int(target_width * aspect_ratio)
        stitched_img = stitched_img.resize((target_width, new_height), Image.Resampling.LANCZOS)

    return stitched_img

def _stitch_horizontal(images, target_width=None):
    """
    Stitch images horizontally. Resizes all to match max height to avoid jagged edges.
    """
    if not images:
        return None
        
    # Find max height
    max_height = max(img.height for img in images)
    
    # Resize images to match max_height (preserving aspect ratio)
    resized_images = []
    total_width = 0
    for img in images:
        if img.height != max_height:
            aspect = img.width / img.height
            new_w = int(max_height * aspect)
            resized = img.resize((new_w, max_height), Image.Resampling.LANCZOS)
            resized_images.append(resized)
            total_width += new_w
        else:
            resized_images.append(img)
            total_width += img.width
            
    # Create canvas
    stitched_img = Image.new('RGB', (total_width, max_height), (255, 255, 255))
    
    current_x = 0
    for img in resized_images:
        stitched_img.paste(img, (current_x, 0))
        current_x += img.width
        
    # Resize if target_width is specified
    if target_width:
        aspect_ratio = max_height / total_width
        new_height = int(target_width * aspect_ratio)
        stitched_img = stitched_img.resize((target_width, new_height), Image.Resampling.LANCZOS)
        
    return stitched_img

def _stitch_grid(images, rows, cols, target_width=None):
    """
    Stitch images into a grid rows x cols. 
    Resizes ALL images to the size of the FIRST image to ensure perfect alignment.
    """
    if not images:
        return None
        
    if rows <= 0: rows = 1
    if cols <= 0: cols = 1
    
    # Use first image as reference size
    ref_w, ref_h = images[0].size
    
    # Limit number of images used to rows * cols
    count = min(len(images), rows * cols)
    used_images = images[:count]
    
    # Create canvas
    canvas_w = ref_w * cols
    canvas_h = ref_h * rows
    stitched_img = Image.new('RGB', (canvas_w, canvas_h), (255, 255, 255))
    
    idx = 0
    for r in range(rows):
        for c in range(cols):
            if idx >= len(used_images):
                break
                
            img = used_images[idx]
            
            # Resize if needed
            if img.size != (ref_w, ref_h):
                img = img.resize((ref_w, ref_h), Image.Resampling.LANCZOS)
                
            x = c * ref_w
            y = r * ref_h
            stitched_img.paste(img, (x, y))
            
            idx += 1
            
    # Resize final output
    if target_width:
        aspect = canvas_h / canvas_w
        new_height = int(target_width * aspect)
        stitched_img = stitched_img.resize((target_width, new_height), Image.Resampling.LANCZOS)
        
    return stitched_img


def stitch_images(image_paths, output_dir, split_count=1, target_width=None, max_kb=None, mode='vertical', rows=2, cols=2, output_format='AUTO'):
    """
    Stitches images based on mode.
    """
    if not image_paths:
        return False, "No images to stitch."

    total_images = len(image_paths)
    
    # Simple Grouping Logic (Consistent with previous step)
    groups = []
    
    if mode == 'grid':
        groups = [image_paths]
    else:
        if split_count > 1:
            avg = len(image_paths) // split_count
            remainder = len(image_paths) % split_count
            start = 0
            for i in range(split_count):
                count = avg + (1 if i < remainder else 0)
                groups.append(image_paths[start:start+count])
                start += count
        else:
            groups = [image_paths]

    saved_files = []
    try:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d")

        # Determine Extension
        ext = ".jpg" # Default
        fmt_arg = 'JPEG'
        
        if output_format == 'PNG':
            ext = ".png"
            fmt_arg = 'PNG'
        elif output_format == 'PDF':
            ext = ".pdf"
            fmt_arg = 'PDF'
        elif output_format == 'AUTO':
            # Use source extension if possible? Or just default to JPG for ease.
            # Let's default to JPG unless user explicit.
            ext = ".jpg"
            fmt_arg = 'JPEG'

        for i, group_paths in enumerate(groups):
            if not group_paths:
                continue

            images = []
            for path in group_paths:
                try:
                    img = Image.open(path)
                    images.append(img)
                except Exception as e:
                    print(f"Warning: Failed to open {path}: {e}")
            
            if not images:
                continue

            result_img = None
            if mode == 'vertical':
                result_img = _stitch_vertical(images, target_width)
            elif mode == 'horizontal':
                result_img = _stitch_horizontal(images, target_width)
            elif mode == 'grid':
                result_img = _stitch_grid(images, rows, cols, target_width)
            
            if result_img:
                base_name = f"stitched_{mode}_{timestamp}_p{i+1}"
                filename = f"{base_name}{ext}"
                output_path = os.path.join(output_dir, filename)
                
                counter = 1
                while os.path.exists(output_path):
                    filename = f"{base_name}_{counter}{ext}"
                    output_path = os.path.join(output_dir, filename)
                    counter += 1
                
                from utils import save_compressed_image
                # Pass format explicitly
                save_compressed_image(result_img, output_path, max_kb, output_format=fmt_arg)
                saved_files.append(filename)

        return True, f"Successfully created {len(saved_files)} images ({mode}, {output_format})."

    except Exception as e:
        return False, f"Error during stitching: {e}"
