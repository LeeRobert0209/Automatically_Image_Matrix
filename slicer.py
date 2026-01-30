import os
from PIL import Image, ImageStat
import math

# Disable the DecompressionBombError for large images
Image.MAX_IMAGE_PIXELS = None

def _is_boundary_solid(image, pos, axis='horizontal'):
    """
    Check if a line at `pos` is visually 'solid' or 'quiet'.
    axis='horizontal': check row at y=pos
    axis='vertical': check col at x=pos
    Returns a score (lower is better/more solid).
    """
    if pos < 0:
        return float('inf')
        
    if axis == 'horizontal':
        if pos >= image.height:
            return float('inf')
        # Crop a 1px high strip: (left, top, right, bottom)
        try:
            boundary_img = image.crop((0, pos, image.width, pos + 1))
        except Exception:
            return float('inf')
    else: # vertical
        if pos >= image.width:
            return float('inf')
        # Crop a 1px wide strip
        try:
            boundary_img = image.crop((pos, 0, pos + 1, image.height))
        except Exception:
            return float('inf')
    
    # Calculate stats
    stat = ImageStat.Stat(boundary_img)
    # Variance of the pixels. Low variance = solid color.
    # We sum the variance of R, G, B
    variance = sum(stat.var)
    return variance

def _find_best_cut(image, target_pos, axis='horizontal', search_range=50):
    """
    Finds the best coordinate to cut near target_pos within search_range.
    """
    limit = image.height if axis == 'horizontal' else image.width
    
    start_pos = max(0, int(target_pos - search_range))
    end_pos = min(limit - 1, int(target_pos + search_range))
    
    best_pos = target_pos
    min_score = float('inf')
    
    # Distance weight
    DIST_WEIGHT = 0.1

    for pos in range(start_pos, end_pos):
        variance = _is_boundary_solid(image, pos, axis)
        
        dist = abs(pos - target_pos)
        weighted_score = variance + (dist * DIST_WEIGHT)
        
        if weighted_score < min_score:
            min_score = weighted_score
            best_pos = pos
            
    return int(best_pos)

def slice_grid_image(image_path, output_dir, rows, cols, target_width=None, max_kb=None, output_format='AUTO', custom_name=None):
    """
    Slices an image into rows x cols grid.
    """
    if not os.path.exists(image_path):
        return False, f"File not found: {image_path}"
        
    try:
        img = Image.open(image_path)
        img.load()
        
        if target_width and target_width != img.width:
            aspect_ratio = img.height / img.width
            new_height = int(target_width * aspect_ratio)
            img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)
            
        width, height = img.size
        cell_width = width / cols
        cell_height = height / rows
        
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        if custom_name:
            base_name = custom_name
            
        specific_output_dir = os.path.join(output_dir, base_name)
        
        if not os.path.exists(specific_output_dir):
            try:
                os.makedirs(specific_output_dir)
            except OSError as e:
                return False, f"Could not create folder '{base_name}': {e}"
        
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
            ext = ".jpg"
            fmt_arg = 'JPEG'

        saved_files = []
        from utils import save_compressed_image
        
        for r in range(rows):
            for c in range(cols):
                left = int(c * cell_width)
                upper = int(r * cell_height)
                # To avoid gaps due to rounding, force last cell to edges
                right = int((c + 1) * cell_width) if c < cols - 1 else width
                lower = int((r + 1) * cell_height) if r < rows - 1 else height
                
                box = (left, upper, right, lower)
                slice_img = img.crop(box)
                
                # Naming
                slice_filename = f"{base_name}_r{r+1:02d}_c{c+1:02d}{ext}"
                output_path = os.path.join(specific_output_dir, slice_filename)
                
                # Use format
                save_compressed_image(slice_img, output_path, max_kb, output_format=fmt_arg)
                saved_files.append(slice_filename)
                
        return True, f"Successfully sliced {len(saved_files)} grid parts ({output_format}) into folder '{base_name}'."
        
    except Exception as e:
        return False, f"Error grid slicing: {e}"

def slice_image(image_path, output_dir, count=1, smart_mode=False, target_width=None, max_kb=None, direction='horizontal', output_format='AUTO', custom_name=None):
    """
    Slices a single image into 'count' pieces.
    """
    if not os.path.exists(image_path):
        return False, f"File not found: {image_path}"
        
    try:
        img = Image.open(image_path)
        
        # Force loading to handle some file types properly
        img.load()
        
        if target_width and target_width != img.width:
            aspect_ratio = img.height / img.width
            new_height = int(target_width * aspect_ratio)
            img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)
        
        if direction == 'horizontal':
            total_length = img.height
        else:
            total_length = img.width
        
        # Calculate cut points
        cut_points = [0]
        
        if count > 1:
            approx_length = total_length / count
            
            for i in range(1, count):
                target_pos = i * approx_length
                
                if smart_mode:
                    search_range = max(50, int(approx_length * 0.4))
                    final_pos = _find_best_cut(img, target_pos, axis=direction, search_range=search_range)
                else:
                    final_pos = int(target_pos)
                
                cut_points.append(final_pos)
        
        cut_points.append(total_length)
        cut_points.sort()
        
        # Ensure we don't have duplicates or out of bounds
        cut_points = sorted(list(set(cut_points)))
        
        # Perform cuts and save
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        if custom_name:
            base_name = custom_name

        specific_output_dir = os.path.join(output_dir, base_name)
        if not os.path.exists(specific_output_dir):
            try:
                os.makedirs(specific_output_dir)
            except OSError as e:
                return False, f"Could not create folder '{base_name}': {e}"

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
            ext = ".jpg"
            fmt_arg = 'JPEG'

        saved_files = []
        from utils import save_compressed_image
        
        for i in range(len(cut_points) - 1):
            start = cut_points[i]
            end = cut_points[i+1]
            
            if end <= start:
                continue
                
            # Crop
            if direction == 'horizontal':
                # (left, top, right, bottom)
                box = (0, start, img.width, end)
            else:
                # Vertical slice: spread across width
                # (left, top, right, bottom)
                box = (start, 0, end, img.height)
                
            slice_img = img.crop(box)
            
            # Save
            if direction == 'horizontal':
                slice_filename = f"{base_name}_{i+1:02d}{ext}"
            else:
                slice_filename = f"{base_name}_v{i+1:02d}{ext}"
                
            output_path = os.path.join(specific_output_dir, slice_filename)
            
            save_compressed_image(slice_img, output_path, max_kb, output_format=fmt_arg)
            saved_files.append(slice_filename)
            
        return True, f"Successfully sliced {len(saved_files)} parts ({direction}, {output_format}) into folder '{base_name}'."
        
    except Exception as e:
        return False, f"Error slicing image: {e}"
