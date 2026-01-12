from PIL import Image
import os
import math

# Disable the DecompressionBombError for large images
Image.MAX_IMAGE_PIXELS = None

def _stitch_single_group(images, target_width=None):
    """
    Helper function to stitch a list of opened PIL images.
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
        # Center the image horizontally if it's smaller than max_width
        x_offset = (max_width - img.width) // 2
        stitched_img.paste(img, (x_offset, current_y))
        current_y += img.height

    # Resize if target_width is specified
    if target_width:
        # Calculate new height to maintain aspect ratio
        aspect_ratio = total_height / max_width
        new_height = int(target_width * aspect_ratio)
        stitched_img = stitched_img.resize((target_width, new_height), Image.Resampling.LANCZOS)

    return stitched_img

def stitch_images(image_paths, output_dir, split_count=1, target_width=None, max_kb=None):
    """
    Stitches images, splitting them into multiple files to balance total height.
    """
    if not image_paths:
        return False, "No images to stitch."

    total_images = len(image_paths)
    if split_count > total_images:
        split_count = total_images
    
    # 1. Pre-calculate heights
    image_infos = [] # List of (path, width, height)
    total_height = 0
    
    try:
        for path in image_paths:
            with Image.open(path) as img:
                # We need to consider the width if we are going to resize later?
                # Actually, for splitting purposes, we assume they will be stitched to same width.
                # So we can just use aspect ratio to normalize height to a common width (e.g. 1000)
                # But simpler: just use raw height if widths are similar. 
                # Better: normalize height to a standard width.
                norm_width = 1000
                aspect = img.height / img.width
                norm_height = norm_width * aspect
                
                image_infos.append({
                    'path': path,
                    'norm_height': norm_height
                })
                total_height += norm_height
    except Exception as e:
        return False, f"Error reading image dimensions: {e}"

    # 2. Determine split points
    target_height_per_group = total_height / split_count
    
    groups = []
    current_group = []
    current_group_height = 0
    
    # We need to create exactly 'split_count' groups.
    # This is a linear partitioning problem. We'll use a greedy approach for simplicity
    # but ensure we don't run out of images for the last groups.
    
    img_idx = 0
    for group_idx in range(split_count):
        # If it's the last group, take everything remaining
        if group_idx == split_count - 1:
            groups.append(image_paths[img_idx:])
            break
            
        current_group = []
        current_group_height = 0
        
        while img_idx < total_images:
            # Check if we must save images for remaining groups
            remaining_images = total_images - img_idx
            remaining_groups = split_count - group_idx
            if remaining_images <= remaining_groups - 1:
                 # Must stop to leave at least 1 image for each remaining group
                 break

            info = image_infos[img_idx]
            
            # Check if adding this image makes us closer to target or further?
            # If current is empty, must add.
            if not current_group:
                current_group.append(info['path'])
                current_group_height += info['norm_height']
                img_idx += 1
                continue
            
            # Calculate difference if we add vs if we don't
            diff_without = abs(target_height_per_group - current_group_height)
            diff_with = abs(target_height_per_group - (current_group_height + info['norm_height']))
            
            if diff_with < diff_without:
                # Adding makes it closer (or equal), so add it
                current_group.append(info['path'])
                current_group_height += info['norm_height']
                img_idx += 1
            else:
                # Adding makes it worse (too tall), so stop here
                break
        
        groups.append(current_group)

    # 3. Stitch each group
    saved_files = []
    try:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d")

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

            result_img = _stitch_single_group(images, target_width)
            
            if result_img:
                # Generate base filename without time (e.g., stitched_20231027_p1.jpg)
                base_name = f"stitched_{timestamp}_p{i+1}"
                ext = ".jpg"
                filename = f"{base_name}{ext}"
                output_path = os.path.join(output_dir, filename)
                
                # Check for existing file and append counter if needed
                counter = 1
                while os.path.exists(output_path):
                    filename = f"{base_name}_{counter}{ext}"
                    output_path = os.path.join(output_dir, filename)
                    counter += 1
                
                # Use the new compression utility
                from utils import save_compressed_image
                save_compressed_image(result_img, output_path, max_kb)
                saved_files.append(filename)

        return True, f"Successfully created {len(saved_files)} images."

    except Exception as e:
        return False, f"Error during stitching: {e}"
