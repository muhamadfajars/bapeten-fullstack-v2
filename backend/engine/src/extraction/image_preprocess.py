import cv2
import numpy as np


def load_image(image_path):
    """
    Membaca gambar dari file.
    """

    image = cv2.imread(image_path)

    if image is None:
        raise ValueError(
            f"Gambar tidak dapat dibaca: {image_path}"
        )

    return image


def ensure_bgr(image):
    """
    Memastikan gambar memiliki 3 channel BGR.

    PaddleOCR pipeline yang kita gunakan membutuhkan:
    (height, width, 3)

    bukan grayscale:
    (height, width)
    """

    if len(image.shape) == 2:
        image = cv2.cvtColor(
            image,
            cv2.COLOR_GRAY2BGR
        )

    return image


def crop_image(
    image,
    top=0.0,
    bottom=1.0,
    left=0.0,
    right=1.0
):
    """
    Crop berdasarkan rasio.

    Contoh:
    top=0.45
    berarti membuang 45% bagian atas.
    """

    h, w = image.shape[:2]

    y1 = int(h * top)
    y2 = int(h * bottom)

    x1 = int(w * left)
    x2 = int(w * right)

    return image[
        y1:y2,
        x1:x2
    ].copy()


def upscale_image(
    image,
    scale=3
):
    """
    Memperbesar gambar menggunakan bicubic interpolation.
    """

    return cv2.resize(
        image,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_CUBIC
    )


def apply_clahe(
    image,
    clip_limit=2.0,
    tile_grid_size=(8, 8)
):
    """
    Meningkatkan local contrast.

    Output dikembalikan ke BGR supaya aman
    untuk PaddleOCR.
    """

    gray = cv2.cvtColor(
        ensure_bgr(image),
        cv2.COLOR_BGR2GRAY
    )

    clahe = cv2.createCLAHE(
        clipLimit=clip_limit,
        tileGridSize=tile_grid_size
    )

    enhanced = clahe.apply(gray)

    return cv2.cvtColor(
        enhanced,
        cv2.COLOR_GRAY2BGR
    )


def sharpen_image(image):
    """
    Sharpen sederhana.
    """

    image = ensure_bgr(image)

    kernel = np.array([
        [0, -1, 0],
        [-1, 5, -1],
        [0, -1, 0]
    ])

    return cv2.filter2D(
        image,
        -1,
        kernel
    )


def create_ocr_variants(
    image_path,
    crop_config=None
):
    """
    Menghasilkan beberapa versi gambar untuk eksperimen OCR.

    crop_config contoh:

    {
        "top": 0.45,
        "bottom": 1.0,
        "left": 0.0,
        "right": 1.0
    }
    """

    original = load_image(
        image_path
    )

    variants = {
        "original": original
    }

    # Kalau belum punya area crop tertentu,
    # cukup kembalikan original.
    if crop_config is None:
        return variants


    crop = crop_image(
        original,
        top=crop_config.get(
            "top",
            0.0
        ),
        bottom=crop_config.get(
            "bottom",
            1.0
        ),
        left=crop_config.get(
            "left",
            0.0
        ),
        right=crop_config.get(
            "right",
            1.0
        )
    )


    variants[
        "crop"
    ] = crop


    crop_upscaled = upscale_image(
        crop,
        scale=4
    )

    variants[
        "crop_upscaled"
    ] = crop_upscaled


    crop_clahe = apply_clahe(
        crop_upscaled
    )

    variants[
        "crop_upscaled_clahe"
    ] = crop_clahe


    crop_sharpen = sharpen_image(
        crop_clahe
    )

    variants[
        "crop_upscaled_clahe_sharpen"
    ] = crop_sharpen


    return variants

def label_roi_variants(image, box, padding=12, scale=2, methods=None):
    """Preprocess only one bounded OCR region; source characters are never changed.

    Baseline is OCR on the original full page; this yields additional candidates.
    """
    image = ensure_bgr(image)
    points = np.asarray(box, dtype=float)
    if points.size < 4:
        return []
    if points.ndim == 1:
        x1, y1, x2, y2 = points[:4]
    else:
        xy = points.reshape(-1, 2)
        x1, y1 = xy.min(axis=0)
        x2, y2 = xy.max(axis=0)
    h, w = image.shape[:2]
    mx = max(padding, int((x2-x1)*.16))
    my = max(padding, int((y2-y1)*.70))
    xa, ya = max(0, int(x1-mx)), max(0, int(y1-my))
    xb, yb = min(w, int(x2+mx)), min(h, int(y2+my))
    if xb <= xa or yb <= ya:
        return []
    crop = image[ya:yb, xa:xb].copy()
    if not crop.size:
        return []
    # No resize by default: benchmarking showed full-page 2x was expensive.
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    variants = {
        'roi_gray': ensure_bgr(gray),
        'roi_clahe': apply_clahe(crop),
        'roi_sharpen': sharpen_image(crop),
        'roi_adaptive': ensure_bgr(cv2.adaptiveThreshold(
            gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,31,11)),
    }
    methods = methods or ('roi_gray','roi_clahe','roi_sharpen','roi_adaptive')
    return [(method, variants[method]) for method in methods if method in variants]
