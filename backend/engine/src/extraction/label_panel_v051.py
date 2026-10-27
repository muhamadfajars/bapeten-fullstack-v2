"""Conservative segmentation of multiple *physical stickers* in a photograph.

No document values are inferred from the image by segmentation. Regions retain
source_id/page for evidence provenance. If segmentation is uncertain, read the
entire image, preserving the v0.5.0 baseline.
"""
import cv2
import numpy as np


def detect_sticker_panels(image):
    if image is None or not hasattr(image, 'shape'):
        return []
    height, width = image.shape[:2]
    if min(height, width) < 350:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    # Large, bright label surfaces are separated from darker metal background.
    blur = cv2.GaussianBlur(gray, (31, 31), 0)
    mask = np.uint8(blur > 175) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (45, 45))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    candidates = []
    for x,y,w,h,area in stats[1:]:
        if not (w >= .45*width and h >= .15*height and area >= .11*height*width):
            continue
        if w*h >= .92*height*width:
            continue  # Plain white PDF page is not a segmented physical sticker.
        if area < .48*w*h:
            continue
        candidates.append((int(x),int(y),int(w),int(h)))
    candidates.sort(key=lambda r: (r[1],r[0]))
    if not (2 <= len(candidates) <= 6):
        return []
    # Decline ambiguous overlapping region detections.
    for a,b in zip(candidates,candidates[1:]):
        overlap_y=max(0,min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1]))
        if overlap_y > .20*min(a[3],b[3]):
            return []
    result=[]
    for x,y,w,h in candidates:
        margin=max(8,round(.013*min(height,width)))
        xa=max(0,x-margin); ya=max(0,y-margin)
        xb=min(width,x+w+margin); yb=min(height,y+h+margin)
        result.append((xa,ya,xb,yb))
    return result
