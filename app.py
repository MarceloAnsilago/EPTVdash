import os
from io import BytesIO
from xml.sax.saxutils import escape

from datetime import datetime
from decimal import Decimal

import pandas as pd
import pymupdf
import streamlit as st
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from supabase import create_client

from ptv_parser import extract_ptv


def preparar_dados(rows):
    campos = {"Nº PTV": "numero_ptv", "Nome do destinatário": "nome_destinatario", "CPF/CNPJ do destinatário": "cpf_cnpj_destinatario", "Endereço de destino": "endereco_destino", "Município de destino": "municipio_destino", "UF de destino": "uf_destino", "Data de emissão": "data_emissao", "Validade": "data_validade", "Nota fiscal": "nota_fiscal"}
    itens = {"Quantidade": "quantidade", "Documento de origem": "documento_origem", "Número do documento": "numero_documento"}
    dados = {destino: rows[0].get(origem, "") for origem, destino in campos.items()}
    if not dados["numero_ptv"]:
        raise ValueError("Número da PTV ausente")
    for campo in ("data_emissao", "data_validade"):
        if dados[campo]:
            dados[campo] = datetime.strptime(dados[campo], "%d/%m/%Y").date().isoformat()
    produtos = [{destino: row.get(origem, "") for origem, destino in itens.items()} for row in rows]
    for produto in produtos:
        produto["quantidade"] = produto["quantidade"].replace(".", "").replace(",", ".")
    return dados, produtos

load_dotenv()
st.set_page_config(page_title="EPTV Dash", page_icon="📊", layout="wide")
st.markdown("""
<style>
    .block-container { max-width: 1500px; padding-top: 2rem; }
    [data-testid="stSidebar"] { border-right: 1px solid rgba(128,128,128,.18); }
    [data-testid="stSidebar"] .stButton button {
        justify-content: flex-start; border-radius: .65rem;
        padding: .65rem 1rem; font-weight: 600;
    }
    [data-testid="stSidebar"] .stButton button[kind="primary"] {
        background: #087e63; border-color: #087e63; color: white;
    }
    [data-testid="stMetric"] {
        background: rgba(8,126,99,.08); border: 1px solid rgba(8,126,99,.15);
        border-radius: .8rem; padding: 1rem 1.2rem;
    }
</style>
""", unsafe_allow_html=True)

def config_value(name):
    value = os.getenv(name)
    if value:
        return value
    try:
        return st.secrets.get(name)
    except FileNotFoundError:
        return None


def formatar_numero(valor, casas=2):
    return f"{valor:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def tabela_ptvs(registros):
    linhas = []
    for ptv in registros:
        for produto in ptv.get("ptv_produtos") or [{}]:
            linhas.append({
                "Nome do destinatário": ptv.get("nome_destinatario"),
                "CPF/CNPJ do destinatário": ptv.get("cpf_cnpj_destinatario"),
                "Endereço de destino": ptv.get("endereco_destino"),
                "Município de destino": ptv.get("municipio_destino"),
                "UF de destino": ptv.get("uf_destino"),
                "Quantidade": produto.get("quantidade"),
                "Documento de origem": produto.get("documento_origem"),
                "Número do documento": produto.get("numero_documento"),
                "Nº PTV": ptv.get("numero_ptv"),
                "Data de emissão": ptv.get("data_emissao"),
                "Validade": ptv.get("data_validade"),
                "Nota fiscal": ptv.get("nota_fiscal"),
            })
    tabela = pd.DataFrame(linhas)
    if not tabela.empty:
        for coluna in ("Data de emissão", "Validade"):
            tabela[coluna] = pd.to_datetime(tabela[coluna], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")
    return tabela


def gerar_relatorio(tabela, total_ptvs, mudas, valor_unitario, percentual, total, valor_final):
    arquivo = BytesIO()
    doc = SimpleDocTemplate(arquivo, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm)
    estilos = getSampleStyleSheet()
    texto = ParagraphStyle("celula", parent=estilos["BodyText"], fontSize=9, leading=12, wordWrap="CJK")
    titulo_celula = ParagraphStyle("rotulo", parent=texto, textColor=colors.HexColor("#31594e"), fontName="Helvetica-Bold")
    titulo = ParagraphStyle("titulo", parent=estilos["Title"], textColor=colors.HexColor("#087e63"), alignment=TA_CENTER)
    elementos = [Paragraph("Relatório de PTVs", titulo), Spacer(1, 5*mm)]
    resumo = [
        ("PTVs cadastradas", formatar_numero(total_ptvs, 0)),
        ("Quantidade de mudas", formatar_numero(mudas, 0 if mudas == mudas.to_integral_value() else 2)),
        ("Valor por muda", "R$ " + formatar_numero(Decimal(str(valor_unitario)))),
        ("Percentual", formatar_numero(Decimal(str(percentual))) + "%"),
        ("Valor total", "R$ " + formatar_numero(total)),
        ("Valor final", "R$ " + formatar_numero(valor_final)),
    ]
    resumo_tabela = Table([[Paragraph(escape(k), titulo_celula), Paragraph(escape(v), texto)] for k, v in resumo], colWidths=[65*mm, 115*mm])
    resumo_tabela.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eff8f4")), ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cfe2d9")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    elementos += [resumo_tabela, Spacer(1, 7*mm), Paragraph("Detalhamento das PTVs", estilos["Heading2"])]
    if tabela.empty:
        elementos.append(Paragraph("Nenhuma PTV cadastrada.", texto))
    for numero, (_, row) in enumerate(tabela.fillna("").iterrows(), 1):
        elementos.append(Paragraph(f"Registro {numero}", estilos["Heading3"]))
        dados = [[Paragraph(escape(str(campo)), titulo_celula), Paragraph(escape(str(valor)) or "—", texto)] for campo, valor in row.items()]
        detalhes = Table(dados, colWidths=[65*mm, 115*mm], splitByRow=1, splitInRow=1)
        detalhes.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#d5e2dc")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f8fbf9")]), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        elementos.extend([detalhes, Spacer(1, 4*mm)])
    def rodape(canvas, documento):
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 15*mm, 9*mm, f"Página {documento.page}")
    doc.build(elementos, onFirstPage=rodape, onLaterPages=rodape)
    return arquivo.getvalue()


def exibir_dashboard(client):
    st.title("Dashboard")
    st.caption("Acompanhe suas PTVs e calcule o valor a receber.")
    with st.container(border=True):
        st.subheader("Parâmetros do cálculo")
        primeira, segunda = st.columns(2)
        with primeira:
            valor_unitario = st.number_input("Valor por muda (R$)", min_value=0.0, value=1.50, step=0.10, format="%.2f")
        with segunda:
            percentual = st.number_input("Seu percentual (%)", min_value=0.0, value=7.0, step=0.5, format="%.2f")
        st.caption("Os valores podem ser alterados durante a sessão.")

    if not st.session_state.get("usuario"):
        st.info("Entre na sua conta para visualizar os dados das PTVs salvas.")
        return
    try:
        registros = []
        inicio = 0
        while True:
            pagina = (client.table("ptvs").select("id,numero_ptv,nome_destinatario,cpf_cnpj_destinatario,endereco_destino,municipio_destino,uf_destino,data_emissao,data_validade,nota_fiscal,ptv_produtos(quantidade,documento_origem,numero_documento)")
                      .order("id").range(inicio, inicio + 499).execute().data)
            registros.extend(pagina)
            if len(pagina) < 500:
                break
            inicio += len(pagina)
        mudas = sum((Decimal(str(produto["quantidade"])) for ptv in registros
                     for produto in ptv.get("ptv_produtos") or []
                     if produto.get("quantidade") is not None), Decimal("0"))
    except Exception:
        st.error("Não foi possível carregar os dados do dashboard. Verifique a conexão com o banco.")
        return

    total = mudas * Decimal(str(valor_unitario))
    valor_final = total * Decimal(str(percentual)) / Decimal("100")
    quantidade = formatar_numero(mudas, 0 if mudas == mudas.to_integral_value() else 2)
    st.subheader("Visão geral")
    cards = st.columns(4)
    cards[0].metric("PTVs cadastradas", formatar_numero(len(registros), 0))
    cards[1].metric("Quantidade de mudas", quantidade)
    cards[2].metric("Valor total", "R$ " + formatar_numero(total), help="Quantidade de mudas multiplicada pelo valor por muda.")
    cards[3].metric("Seu valor final", "R$ " + formatar_numero(valor_final), help="Percentual aplicado ao valor total.")
    st.divider()
    st.subheader("PTVs cadastradas")
    tabela = tabela_ptvs(registros)
    if tabela.empty:
        st.info("Nenhuma PTV salva até agora.")
    else:
        st.dataframe(tabela, hide_index=True, width="stretch")
    pdf = gerar_relatorio(tabela, len(registros), mudas, valor_unitario, percentual, total, valor_final)
    st.download_button("📄 Baixar relatório em PDF", pdf, file_name="relatorio_ptvs.pdf", mime="application/pdf", type="primary")


def exibir_ptvs_salvas(client):
    st.title("PTVs salvas")
    st.caption("Consulte os documentos cadastrados e gerencie seus registros.")
    if not st.session_state.get("usuario"):
        st.info("Entre na sua conta para consultar as PTVs salvas.")
        return
    try:
        registros = (client.table("ptvs")
                     .select("id,numero_ptv,nome_destinatario,cpf_cnpj_destinatario,endereco_destino,municipio_destino,uf_destino,data_emissao,data_validade,nota_fiscal,ptv_produtos(quantidade,documento_origem,numero_documento)")
                     .order("id", desc=True).execute().data)
    except Exception:
        st.error("Não foi possível consultar as PTVs. Verifique sua conexão e as permissões do banco.")
        return
    if not registros:
        st.info("Nenhuma PTV salva até agora.")
        return

    st.metric("PTVs cadastradas", len(registros))
    tabela = tabela_ptvs(registros)
    st.dataframe(tabela, hide_index=True, width="stretch")
    st.download_button("Baixar PTVs em CSV", tabela.to_csv(index=False, sep=";").encode("utf-8-sig"), file_name="ptvs_salvas.csv", mime="text/csv")

    with st.expander("Excluir uma PTV"):
        st.caption("A exclusão também remove os produtos vinculados à PTV.")
        opcoes = {p["id"]: f"{p['numero_ptv']} — {p.get('nome_destinatario') or 'Destinatário não informado'}" for p in registros}
        selecionado = st.selectbox("Selecione a PTV", list(opcoes), format_func=opcoes.get)
        confirmar = st.checkbox("Confirmo a exclusão desta PTV e de seus produtos", key=f"confirmar_{selecionado}")
        if st.button("Excluir PTV selecionada", disabled=not confirmar):
            try:
                resultado = client.table("ptvs").delete().eq("id", selecionado).execute()
                if not resultado.data:
                    st.error("A PTV não foi excluída. Verifique as permissões do banco.")
                else:
                    st.session_state.ptv_excluida = opcoes[selecionado]
                    st.rerun()
            except Exception:
                st.error("Não foi possível excluir a PTV. Verifique a conexão e as permissões do banco.")


url = config_value("SUPABASE_URL")
key = config_value("SUPABASE_KEY")
if "supabase_client" not in st.session_state and url and key:
    st.session_state.supabase_client = create_client(url, key)
client = st.session_state.get("supabase_client")

with st.sidebar:
    st.title("📊 EPTV Dash")
    st.caption("Permissão de Trânsito de Vegetais")
    st.divider()
    st.caption("NAVEGAÇÃO")
    if "pagina" not in st.session_state:
        st.session_state.pagina = "Dashboard"
    for nome, icone in (("Dashboard", "📊"), ("Ler PTV", "📄"), ("PTVs salvas", "🗂️")):
        if st.button(f"{icone}  {nome}", key=f"nav_{nome}", width="stretch", type="primary" if st.session_state.pagina == nome else "secondary"):
            st.session_state.pagina = nome
            st.rerun()
    pagina = st.session_state.pagina
    st.divider()
    st.subheader("Minha conta")
    if client:
        if st.session_state.get("usuario"):
            st.success("Conectado: " + st.session_state.usuario)
            if st.button("Sair"):
                client.auth.sign_out()
                del st.session_state.usuario
                st.rerun()
        else:
            with st.form("login"):
                email = st.text_input("E-mail")
                senha = st.text_input("Senha", type="password")
                entrar = st.form_submit_button("Entrar")
            if entrar:
                try:
                    response = client.auth.sign_in_with_password({"email": email, "password": senha})
                    st.session_state.usuario = response.user.email
                    st.rerun()
                except Exception:
                    st.error("Não foi possível entrar. Confira o e-mail, a senha e a configuração do Supabase.")
    else:
        st.info("Configure SUPABASE_URL e SUPABASE_KEY no arquivo .env.")

if pagina == "Dashboard":
    exibir_dashboard(client)
elif pagina == "PTVs salvas":
    if st.session_state.get("ptv_excluida"):
        st.success("PTV excluída: " + st.session_state.pop("ptv_excluida"))
    exibir_ptvs_salvas(client)
else:
    st.title("Ler uma PTV")
    st.caption("Envie um PDF para conferir os dados e salvar o documento.")
    upload = st.file_uploader("Arraste ou selecione o PDF da PTV", type=["pdf"])
    if upload is not None:
        try:
            with pymupdf.open(stream=upload.getvalue(), filetype="pdf") as document:
                if document.needs_pass:
                    st.warning("Este PDF está protegido por senha.")
                else:
                    text = "\n\n".join(page.get_text() for page in document).strip()
                    if not text:
                        st.warning("Nenhum texto encontrado. PDFs digitalizados podem precisar de OCR.")
                    else:
                        rows = extract_ptv(text)
                        if rows:
                            st.caption("Confira os dados extraídos no documento original. Campos não identificados ficam vazios.")
                            colunas = ["Nome do destinatário", "CPF/CNPJ do destinatário", "Endereço de destino", "Município de destino", "UF de destino", "Quantidade", "Documento de origem", "Número do documento", "Nº PTV", "Data de emissão", "Validade", "Nota fiscal"]
                            tabela = pd.DataFrame(rows).reindex(columns=colunas)
                            st.dataframe(tabela, hide_index=True, width="stretch")
                            st.download_button("Baixar tabela em CSV", tabela.to_csv(index=False, sep=";").encode("utf-8-sig"), file_name="ptv.csv", mime="text/csv")
                            if st.session_state.get("usuario"):
                                if st.button("Salvar PTV no banco"):
                                    try:
                                        dados, produtos = preparar_dados(rows)
                                        client.rpc("salvar_ptv", {"dados": dados, "produtos": produtos}).execute()
                                        st.success("PTV salva no banco de dados.")
                                    except Exception:
                                        st.error("Não foi possível salvar. Verifique se a PTV já foi cadastrada e se o script de acesso foi executado.")
                            else:
                                st.info("Entre na sua conta para salvar a PTV no banco.")
                        else:
                            st.warning("Modelo de PTV não reconhecido. Confira o texto extraído abaixo.")
                        with st.expander("Ver texto extraído do PDF"):
                            st.text(text)
        except (pymupdf.FileDataError, pymupdf.EmptyFileError, ValueError):
            st.error("Não foi possível ler este PDF. Verifique se o arquivo é válido.")



def get_supabase_client():
    """Cria o cliente quando a integração com o banco for necessária."""
    if not url or not key:
        raise ValueError("Configure SUPABASE_URL e SUPABASE_KEY no arquivo .env.")
    return create_client(url, key)
