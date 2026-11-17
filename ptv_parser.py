"""Extração dos campos do modelo de PTV da IDARON."""
import re


def _section(text, start, end):
    match = re.search(start + r"(.*?)" + end, text, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def _match(pattern, text):
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def extract_ptv(text):
    """Retorna uma linha por produto; campos não reconhecidos ficam vazios."""
    if not re.search(r"PERMISS[ÃA]O DE TR[ÂA]NSITO DE VEGETAIS", text, re.I):
        return []

    interested = _lines(_section(text, r"Nome do Interessado\s*CPF/CNPJ", r"Munic[íi]pio\s*UF\s*Endere[çc]o"))
    origin = _lines(_section(text, r"Munic[íi]pio\s*UF\s*Endere[çc]o", r"DADOS DO PRODUTO"))
    destination = _lines(_section(text, r"Nome do destinat[áa]rio\s*CPF/CNPJ", r"DECLARA[ÇC][ÃA]O ADICIONAL"))
    recipient = [line for line in destination if not re.fullmatch(r"Endere[çc]o|Munic[íi]pio|UF", line, re.I)]
    declaration_lines = _lines(_section(text, r"DECLARA[\u00c7C][\u00c3A]O ADICIONAL", r"\nN[\u00e3a]o\s*\n"))
    destination_address = ""
    if len(recipient) == 4 and len(declaration_lines) > 1:
        destination_address = declaration_lines.pop()
        recipient.insert(2, destination_address)
    product_lines = _lines(_section(text, r"Nome cient[íi]fico\s*Cultivar\s*Clone", r"Ordem\s*Unidade Produ[çc][ãa]o"))
    quantity_lines = _lines(_section(text, r"Cfo/Cfoc/Ptv/Cf/Cfr\s*N[úu]mero\s*TF n[ºo°]", r"Partida lacrada"))

    # O PDF apresenta os dados de cada tabela na ordem visual das colunas.
    def records(lines, columns):
        groups = []
        for line in lines:
            if re.fullmatch(r"\d+", line) and (not groups or len(groups[-1]) >= columns):
                groups.append([line])
            elif groups:
                groups[-1].append(line)
        return groups

    products = records(product_lines, 6)
    quantities = records(quantity_lines, 7)
    base = {
        "Nº PTV": _match(r"PERMISS[ÃA]O DE TR[ÂA]NSITO DE VEGETAIS\s*N\.\s*[oº°:]?\s*:?\s*(\d+)", text),
        "Nome do remetente": interested[0] if len(interested) > 0 else "",
        "CPF/CNPJ do remetente": interested[1] if len(interested) > 1 else "",
        "Endereço de origem": origin[0] if len(origin) > 0 else "",
        "Município de origem": origin[1] if len(origin) > 1 else "",
        "UF de origem": origin[2] if len(origin) > 2 else "",
        "Nome do destinatário": recipient[0] if len(recipient) > 0 else "",
        "CPF/CNPJ do destinatário": recipient[1] if len(recipient) > 1 else "",
        "Endereço de destino": recipient[2] if len(recipient) > 2 else "",
        "Município de destino": recipient[3] if len(recipient) > 3 else "",
        "UF de destino": recipient[4] if len(recipient) > 4 else "",
        "Data de emissão": _match(r"Local e Data.*?\b(\d{2}/\d{2}/\d{4})", text),
        "Validade": _match(r"Validade\s*(\d{2}/\d{2}/\d{4})", text),
        "Itinerário": _match(r"Itiner[áa]rio:\s*(.*?)\s*Apresenta[çc][ãa]o da Nota Fiscal", text),
        "Nota fiscal": _match(r"N[úu]mero da Nota Fiscal:\s*(\d+)", text),
        "Declaração adicional": _match(r"DECLARA[ÇC][ÃA]O ADICIONAL\s*(.*?)(?:\nN[ãa]o\s*\n|\n[A-F0-9]{20,}\s*\n|\nValidade)", text),
    }
    rows = []
    for index in range(max(len(products), len(quantities), 1)):
        product = products[index] if index < len(products) else []
        quantity = quantities[index] if index < len(quantities) else []
        value = lambda row, i: row[i] if len(row) > i else ""
        rows.append({**base, "Produto": value(product, 1), "Nome vulgar": value(product, 2),
                     "Nome científico": value(product, 3), "Cultivar": value(product, 4),
                     "Unidade de produção": value(quantity, 1), "Quantidade": value(quantity, 2),
                     "Medida": value(quantity, 3), "Documento de origem": value(quantity, 4),
                     "Número do documento": value(quantity, 5)})
    return rows
