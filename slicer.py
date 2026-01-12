import os
from PIL import Image, ImageStat
import math

# Disable the DecompressionBombError for large images
Image.MAX_IMAGE_PIXELS = None

def _is_line_solid(image, y, threshold=10):
    """
    Check if a horizontal line at y is visually 'solid' or 'quiet'.
    Returns a score (lower is better/more solid).
    """
    # Get the pixel data for the row
    # Crop a 1px high strip
    if y < 0 or y >= image.height:
        return float('inf')
        
    row_img = image.crop((0, y, image.width, y + 1))
    
    # Calculate stats
    stat = ImageStat.Stat(row_img)
    # Variance of the row's pixels. Low variance = solid color.
    # We sum the variance of R, G, B
    variance = sum(stat.var)
    return variance

def _find_best_cut(image, target_y, search_range=50):
    """
    Finds the best Y coordinate to cut near target_y within search_range.
    Prioritizes low-variance (solid color) rows.
    """
    start_y = max(0, int(target_y - search_range))
    end_y = min(image.height - 1, int(target_y + search_range))
    
    best_y = target_y
    min_score = float('inf')
    
    # Distance weight: higher means we stick closer to target_y
    # Standard variance for a high-contrast line can be huge (e.g. > 1000).
    # Distance penalty of 0.5 per pixel means 50px away = +25 score.
    # This should be enough to jump over text, but let's make sure.
    
    DIST_WEIGHT = 0.1 # Reduced from 0.5 to allow searching further for better cuts

    for y in range(start_y, end_y):
        variance = _is_line_solid(image, y)
        
        # If variance is effectively 0 (solid color), it's a perfect cut candidate.
        # We still apply a small distance penalty to choose the CLOSEST solid line.
        
        dist = abs(y - target_y)
        weighted_score = variance + (dist * DIST_WEIGHT)
        
        if weighted_score < min_score:
            min_score = weighted_score
            best_y = y
            
    return int(best_y)

def slice_image(image_path, output_dir, count=1, smart_mode=False, target_width=None, max_kb=None):
    """
    Slices a single image into 'count' pieces.
    
    Args:
        image_path (str): Path to source image.
        output_dir (str): Directory to save slices.
        count (int): Number of slices.
        smart_mode (bool): If True, tries to cut at visual boundaries.
        target_width (int): Optional. Resize image to this width before slicing.
        max_kb (int, optional): Max size in KB.
        
    Returns:
        (bool, str): Success status and message.
    """
    if not os.path.exists(image_path):
        return False, f"File not found: {image_path}"
        
    try:
        img = Image.open(image_path)
        
        # Force loading to handle some file types properly
        img.load()
        
        # Resize if needed
        if target_width and target_width != img.width:
            aspect_ratio = img.height / img.width
            new_height = int(target_width * aspect_ratio)
            img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)
        
        total_height = img.height
        
        # Calculate cut points
        cut_points = [0]
        
        if count > 1:
            approx_height = total_height / count
            
            for i in range(1, count):
                target_y = i * approx_height
                
                if smart_mode:
                    # Smart adjustment
                    # Search range depends on image size, e.g., 5% of height or fixed 50-100px
                    search_range = max(50, int(approx_height * 0.4)) # Increased range from 0.15 to 0.4
                    final_y = _find_best_cut(img, target_y, search_range)
                else:
                    final_y = int(target_y)
                
                cut_points.append(final_y)
        
        cut_points.append(total_height)
        cut_points.sort()
        
        # Ensure we don't have duplicates or out of bounds (sanity check)
        cut_points = sorted(list(set(cut_points)))
        
        # Perform cuts and save
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        
        # User Request: Create a folder with the image name to store slices
        specific_output_dir = os.path.join(output_dir, base_name)
        if not os.path.exists(specific_output_dir):
            try:
                os.makedirs(specific_output_dir)
            except OSError as e:
                return False, f"Could not create folder '{base_name}': {e}"

        saved_files = []
        from utils import save_compressed_image
        
        for i in range(len(cut_points) - 1):
            upper = cut_points[i]
            lower = cut_points[i+1]
            
            if lower <= upper:
                continue
                
            # Crop: (left, upper, right, lower)
            box = (0, upper, img.width, lower)
            slice_img = img.crop(box)
            
            # Save
            # Naming convention: SourceName_01.jpg
            slice_filename = f"{base_name}_{i+1:02d}.jpg"
            output_path = os.path.join(specific_output_dir, slice_filename)
            
            save_compressed_image(slice_img, output_path, max_kb)
            saved_files.append(slice_filename)
            
        return True, f"Successfully sliced {len(saved_files)} parts into folder '{base_name}'."
        
    except Exception as e:
        return False, f"Error slicing image: {e}"
