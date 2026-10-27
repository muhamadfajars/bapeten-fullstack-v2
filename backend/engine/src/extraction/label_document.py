import os

import cv2
import pymupdf
import numpy as np


SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp",
}


def get_file_extension(file_path):

    extension = os.path.splitext(
        file_path
    )[1]

    return extension.lower()


def load_image_file(file_path):

    image = cv2.imread(
        file_path
    )

    if image is None:

        raise ValueError(
            f"Gagal membaca image: {file_path}"
        )

    return image


def render_pdf_pages(
    pdf_path,
    dpi=200
):

    doc = pymupdf.open(
        pdf_path
    )

    results = []

    try:

        zoom = dpi / 72

        matrix = pymupdf.Matrix(
            zoom,
            zoom
        )

        for page_index, page in enumerate(
            doc
        ):

            pixmap = page.get_pixmap(
                matrix=matrix,
                alpha=False
            )

            image_bytes = (
                pixmap.tobytes(
                    "png"
                )
            )

            image_array = np.frombuffer(
                image_bytes,
                dtype=np.uint8
            )

            image = cv2.imdecode(
                image_array,
                cv2.IMREAD_COLOR
            )

            if image is None:
                continue

            results.append({
                "source_type":
                    "pdf",

                "page":
                    page_index + 1,

                "image":
                    image,

                "width":
                    image.shape[1],

                "height":
                    image.shape[0],
            })

    finally:

        doc.close()

    return results


def prepare_label_document(
    file_path,
    pdf_dpi=200
):

    extension = get_file_extension(
        file_path
    )

    if extension in (
        SUPPORTED_IMAGE_EXTENSIONS
    ):

        image = load_image_file(
            file_path
        )

        return [
            {
                "source_type":
                    "image",

                "page":
                    1,

                "image":
                    image,

                "width":
                    image.shape[1],

                "height":
                    image.shape[0],
            }
        ]


    if extension == ".pdf":

        pages = render_pdf_pages(
            file_path,
            dpi=pdf_dpi
        )

        if not pages:

            raise ValueError(
                "PDF berhasil dibuka tetapi "
                "tidak ada halaman yang dapat dirender."
            )

        return pages


    raise ValueError(
        "Format file label tidak didukung. "
        "Gunakan JPG, JPEG, PNG, BMP, WEBP, atau PDF."
    )