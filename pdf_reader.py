"""Leitura de PDFs com OCR para páginas sem camada de texto."""


class OCRUnavailableError(RuntimeError):
    pass


def extract_document_text(document):
    pages = []
    for number, page in enumerate(document, start=1):
        text = page.get_text().strip()
        if not text:
            try:
                textpage = page.get_textpage_ocr(language="por+eng", dpi=300, full=True)
                text = page.get_text(textpage=textpage).strip()
            except RuntimeError as exc:
                raise OCRUnavailableError(
                    f"Não foi possível reconhecer o texto da página {number}. "
                    "Verifique a instalação do Tesseract e dos idiomas português e inglês. "
                    "No Streamlit Cloud, publique o packages.txt e reinicie o aplicativo."
                ) from exc
        pages.append(text)
    return "\n\n".join(pages).strip()
