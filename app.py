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
st.markdown("""
<style>
    .block-container { max-width: 1500px; padding-top: 2rem; }
    [data-testid="stSidebar"] { border-right: 1px solid rgba(128,128,128,.18); }
    [data-testid="stSidebar"] [role="radiogroup"] { gap: .35rem; }
    [data-testid="stSidebar"] [role="radiogroup"] label {
        padding: .65rem .8rem; border-radius: .6rem;
        background: rgba(128,128,128,.08);
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
        background: rgba(0,145,102,.16);
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
    st.metric("PTVs cadastradas", len(registros))
    tabela = pd.DataFrame(linhas)
    for coluna in ("Data de emissão", "Validade"):
        tabela[coluna] = pd.to_datetime(tabela[coluna], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")
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
    pagina = st.radio("Navegação", ["Ler PTV", "PTVs salvas"], format_func=lambda p: {"Ler PTV": "📄  Ler PTV", "PTVs salvas": "🗂️  PTVs salvas"}[p], label_visibility="collapsed")
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

if pagina == "PTVs salvas":
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
