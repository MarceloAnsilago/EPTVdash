"""Leitura de PDFs com OCR para páginas sem camada de texto."""
import cv2
import numpy as np
import pymupdf
import re


def _ocr_page(page, report):
    report(0.1, "Preparando a imagem")
    # Linhas de formulários fazem o Tesseract descartar valores como desenhos.
    pix = page.get_pixmap(dpi=300, colorspace=pymupdf.csGRAY)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()
    binary = cv2.threshold(image, 180, 255, cv2.THRESH_BINARY_INV)[1]
    mask = np.zeros_like(binary)
    for size in ((100, 1), (1, 100)):
        lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN,
                                 cv2.getStructuringElement(cv2.MORPH_RECT, size))
        mask = cv2.bitwise_or(mask, lines)
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))
    image[mask > 0] = 255
    cleaned = pymupdf.Pixmap(pymupdf.csGRAY, pix.width, pix.height, image.tobytes(), False)
    cleaned = pymupdf.Pixmap(pymupdf.csRGB, cleaned)
    report(0.25, "Reconhecendo o texto")
    with pymupdf.open() as temporary:
        target = temporary.new_page(width=page.rect.width, height=page.rect.height)
        target.insert_image(target.rect, pixmap=cleaned)
        textpage = target.get_textpage_ocr(language="por+eng", dpi=300, full=True)
        text = target.get_text(textpage=textpage).strip()
    # Datas em células pequenas podem desaparecer no OCR da página inteira.
    report(0.6, "Localizando os campos de data")
    original = page.get_textpage_ocr(language="por+eng", dpi=300, full=True)
    report(0.8, "Lendo as datas")
    for word in original.extractWORDS():
        if word[4] not in ("Validade", "Local"):
            continue
        label = "Validade" if word[4] == "Validade" else "Local e Data"
        right = page.rect.width - 25 if label == "Validade" else page.rect.width / 2
        clip = pymupdf.Rect(word[0], word[1], right, min(word[1] + 70, page.rect.height))
        if clip.is_empty:
            continue
        with pymupdf.open() as temporary:
            target = temporary.new_page(width=clip.width, height=clip.height)
            target.insert_image(target.rect, pixmap=page.get_pixmap(dpi=300, clip=clip))
            tp = target.get_textpage_ocr(language="por+eng", dpi=300, full=True)
            date = re.search(r"\b\d{2}/\d{2}/\d{4}\b", target.get_text(textpage=tp))
            if date:
                text += "\n" + label + "\n" + date.group()
    return text


class OCRUnavailableError(RuntimeError):
    pass


def extract_document_text(document, on_progress=None):
    """Informa progresso por página e etapa usando callback opcional."""
    pages = []
    total = len(document)
    for number, page in enumerate(document, start=1):
        def report(fraction, stage):
            if on_progress is not None:
                on_progress((number - 1 + fraction) / total,
                            f"Página {number} de {total}: {stage.lower()}...")

        report(0, "Extraindo texto")
        text = page.get_text().strip()
        if not text:
            try:
                text = _ocr_page(page, report)
            except RuntimeError as exc:
                raise OCRUnavailableError(
                    f"Não foi possível reconhecer o texto da página {number}. "
                    "Verifique a instalação do Tesseract e dos idiomas português e inglês. "
                    "No Streamlit Cloud, publique o packages.txt e reinicie o aplicativo."
                ) from exc
        pages.append(text)
        report(1, "Leitura concluída")
    return "\n\n".join(pages).strip()
