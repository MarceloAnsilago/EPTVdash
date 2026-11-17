import os

from datetime import datetime

import pandas as pd
import pymupdf
import streamlit as st
from dotenv import load_dotenv
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
st.title("EPTV Dash")
st.write("Envie uma Permissão de Trânsito de Vegetais (PTV) para consultar seus dados.")

def config_value(name):
    value = os.getenv(name)
    if value:
        return value
    try:
        return st.secrets.get(name)
    except FileNotFoundError:
        return None


url = config_value("SUPABASE_URL")
key = config_value("SUPABASE_KEY")
if "supabase_client" not in st.session_state and url and key:
    st.session_state.supabase_client = create_client(url, key)
client = st.session_state.get("supabase_client")

with st.sidebar:
    st.header("Supabase")
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

st.header("Leitura de PTV")
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
