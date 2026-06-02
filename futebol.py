import streamlit as st
import psycopg2
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 1. FUNÇÕES DE BANCO DE DADOS
# ==========================================
def obter_conexao():
    url_banco = os.getenv("DATABASE_URL")
    return psycopg2.connect(url_banco)

def criar_tabelas():
    conn = obter_conexao()
    conn.autocommit = True 
    c = conn.cursor()
    
    # Criação das tabelas base
    c.execute("""
        CREATE TABLE IF NOT EXISTS partidas (
            id SERIAL PRIMARY KEY,
            data DATE,
            campeao VARCHAR(50),
            local_jogo VARCHAR(255)
        );
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS stats_jogadores (
            id SERIAL PRIMARY KEY,
            partida_id INTEGER REFERENCES partidas(id),
            jogador VARCHAR(100),
            time VARCHAR(50),
            gols INTEGER DEFAULT 0,
            assistencias INTEGER DEFAULT 0
        );
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS stats_goleiros (
            id SERIAL PRIMARY KEY,
            partida_id INTEGER REFERENCES partidas(id),
            goleiro VARCHAR(100),
            time VARCHAR(50),
            gols INTEGER DEFAULT 0,
            assistencias INTEGER DEFAULT 0,
            gols_sofridos INTEGER DEFAULT 0,
            penaltis INTEGER DEFAULT 0,
            penaltis_defendidos INTEGER DEFAULT 0
        );
    """)
    
    try:
        c.execute("ALTER TABLE partidas ADD COLUMN local_jogo VARCHAR(255);")
    except psycopg2.errors.DuplicateColumn:
        pass 
    except Exception:
        pass
        
    conn.close()

# Inicializa as tabelas
criar_tabelas()

# ==========================================
# 2. CONFIGURAÇÃO DA PÁGINA STREAMLIT
# ==========================================
st.set_page_config(page_title="Stats da Pelada", page_icon="⚽", layout="wide")
st.title("⚽ Central de Estatísticas da Pelada")

# Abas de navegação (Agora com o Perfil do Jogador restaurado!)
aba_registro, aba_linha, aba_goleiros, aba_perfil = st.tabs([
    "📝 Registrar Partida", 
    "🏃‍♂️ Classificação Linha", 
    "🧤 Paredões (Goleiros)",
    "👤 Perfil do Jogador"
])

# ==========================================
# 3. ABA: REGISTRAR PARTIDA
# ==========================================
with aba_registro:
    with st.form("registro_partida", clear_on_submit=True):
        st.subheader("Informações da Partida")
        col_data, col_local, col_campeao = st.columns(3)
        data_jogo = col_data.date_input("Data do Jogo")
        local_jogo = col_local.text_input("Local do Jogo (Campo/Quadra)")
        time_campeao = col_campeao.selectbox("Time Campeão", ["Nenhum", "Time A", "Time B"])
        
        st.markdown("---")
        
        # --- TIME A ---
        st.subheader("👕 Time A")
        st.markdown("**动作 Goleiro (Time A)**")
        goleiro_a = st.text_input("Nome do Goleiro A", key="goleiro_a_nome")
        col1, col2, col3, col4, col5 = st.columns(5)
        g_a_gols = col1.number_input("Gols (A)", 0, key="g_a_gols")
        g_a_ast = col2.number_input("Assist. (A)", 0, key="g_a_ast")
        g_a_sof = col3.number_input("Gols Sofridos (A)", 0, key="g_a_sof")
        g_a_pen = col4.number_input("Pênaltis (A)", 0, key="g_a_pen")
        g_a_def = col5.number_input("Pên. Defendidos", 0, key="g_a_def")
        
        st.markdown("**🏃‍♂️ Jogadores de Linha (Time A)**")
        jogadores_a = []
        for i in range(5): 
            col_nome, col_gol, col_ast = st.columns([3, 1, 1])
            nome = col_nome.text_input(f"Jogador {i+1} (A)", key=f"j_a_nome_{i}")
            gols = col_gol.number_input("Gols", 0, key=f"j_a_gol_{i}")
            asts = col_ast.number_input("Assist.", 0, key=f"j_a_ast_{i}")
            if nome:
                jogadores_a.append({"nome": nome, "gols": gols, "assistencias": asts})

        st.markdown("---")
        
        # --- TIME B ---
        st.subheader("👕 Time B")
        st.markdown("**🧤 Goleiro (Time B)**")
        goleiro_b = st.text_input("Nome do Goleiro B", key="goleiro_b_nome")
        col6, col7, col8, col9, col10 = st.columns(5)
        g_b_gols = col6.number_input("Gols (B)", 0, key="g_b_gols")
        g_b_ast = col7.number_input("Assist. (B)", 0, key="g_b_ast")
        g_b_sof = col8.number_input("Gols Sofridos (B)", 0, key="g_b_sof")
        g_b_pen = col9.number_input("Pênaltis (B)", 0, key="g_b_pen")
        g_b_def = col10.number_input("Pên. Defendidos", 0, key="g_b_def")
        
        st.markdown("**🏃‍♂️ Jogadores de Linha (Time B)**")
        jogadores_b = []
        for i in range(5): 
            col_nome, col_gol, col_ast = st.columns([3, 1, 1])
            nome = col_nome.text_input(f"Jogador {i+1} (B)", key=f"j_b_nome_{i}")
            gols = col_gol.number_input("Gols", 0, key=f"j_b_gol_{i}")
            asts = col_ast.number_input("Assist.", 0, key=f"j_b_ast_{i}")
            if nome:
                jogadores_b.append({"nome": nome, "gols": gols, "assistencias": asts})

        salvar = st.form_submit_button("💾 Registrar Partida na Nuvem", use_container_width=True)
        
        if salvar:
            try:
                conn = obter_conexao()
                c = conn.cursor()
                
                c.execute("INSERT INTO partidas (data, campeao, local_jogo) VALUES (%s, %s, %s) RETURNING id", 
                          (data_jogo, time_campeao, local_jogo))
                partida_id = c.fetchone()[0]
                
                if goleiro_a.strip():
                    c.execute("""
                        INSERT INTO stats_goleiros (partida_id, goleiro, time, gols, assistencias, gols_sofridos, penaltis, penaltis_defendidos) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (partida_id, goleiro_a, "Time A", g_a_gols, g_a_ast, g_a_sof, g_a_pen, g_a_def))
                
                if goleiro_b.strip():
                    c.execute("""
                        INSERT INTO stats_goleiros (partida_id, goleiro, time, gols, assistencias, gols_sofridos, penaltis, penaltis_defendidos) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (partida_id, goleiro_b, "Time B", g_b_gols, g_b_ast, g_b_sof, g_b_pen, g_b_def))
                
                for j in jogadores_a:
                    c.execute("INSERT INTO stats_jogadores (partida_id, jogador, time, gols, assistencias) VALUES (%s, %s, %s, %s, %s)",
                              (partida_id, j["nome"], "Time A", j["gols"], j["assistencias"]))
                for j in jogadores_b:
                    c.execute("INSERT INTO stats_jogadores (partida_id, jogador, time, gols, assistencias) VALUES (%s, %s, %s, %s, %s)",
                              (partida_id, j["nome"], "Time B", j["gols"], j["assistencias"]))
                
                conn.commit()
                conn.close()
                st.success("✅ Partida registrada com sucesso!")
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

# ==========================================
# 4. ABA: CLASSIFICAÇÃO DE LINHA
# ==========================================
with aba_linha:
    st.header("🏆 Ranking de Jogadores (Linha)")
    conn = obter_conexao()
    
    query_linha = """
        SELECT 
            s.jogador as "Jogador",
            COUNT(s.partida_id) as "Jogos",
            SUM(CASE WHEN s.time = p.campeao THEN 1 ELSE 0 END) as "Títulos",
            SUM(s.gols) as "Gols",
            SUM(s.assistencias) as "Assistências"
        FROM stats_jogadores s
        JOIN partidas p ON s.partida_id = p.id
        GROUP BY s.jogador
    """
    
    df_linha = pd.read_sql_query(query_linha, conn)
    conn.close()
    
    if not df_linha.empty:
        df_linha["Média Participação/Jogo"] = ((df_linha["Gols"] + df_linha["Assistências"]) / df_linha["Jogos"]).round(2)
        colunas_linha = ["Jogador", "Jogos", "Títulos", "Gols", "Assistências", "Média Participação/Jogo"]
        df_linha = df_linha[colunas_linha]
        df_linha = df_linha.sort_values(by="Média Participação/Jogo", ascending=False)
        st.dataframe(df_linha, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum jogador de linha registrado ainda.")

# ==========================================
# 5. ABA: CLASSIFICAÇÃO GOLEIROS
# ==========================================
with aba_goleiros:
    st.header("🧤 Estatísticas dos Goleiros")
    conn = obter_conexao()
    
    query_goleiros = """
        SELECT 
            sg.goleiro as "Goleiro",
            COUNT(sg.partida_id) as "Jogos",
            SUM(CASE WHEN sg.time = p.campeao THEN 1 ELSE 0 END) as "Títulos",
            SUM(sg.gols_sofridos) as "Gols Sofridos",
            SUM(sg.penaltis) as "Pênaltis Contra",
            SUM(sg.penaltis_defendidos) as "Pên. Defendidos",
            SUM(sg.gols) as "Gols Feitos",
            SUM(sg.assistencias) as "Assistências"
        FROM stats_goleiros sg
        JOIN partidas p ON sg.partida_id = p.id
        GROUP BY sg.goleiro
    """
    
    df_goleiros = pd.read_sql_query(query_goleiros, conn)
    conn.close()

    if not df_goleiros.empty:
        df_goleiros["Média Sofridos/Jogo"] = (df_goleiros["Gols Sofridos"] / df_goleiros["Jogos"]).round(2)
        df_goleiros["% Pên. Defendidos"] = (df_goleiros["Pên. Defendidos"] / df_goleiros["Pênaltis Contra"] * 100).fillna(0).round(1).astype(str) + "%"
        colunas_finais = [
            "Goleiro", "Jogos", "Títulos", "Gols Sofridos", "Média Sofridos/Jogo",
            "Pênaltis Contra", "Pên. Defendidos", "% Pên. Defendidos", 
            "Gols Feitos", "Assistências"
        ]
        df_goleiros = df_goleiros[colunas_finais].sort_values(by="Média Sofridos/Jogo", ascending=True)
        st.dataframe(df_goleiros, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum goleiro registrado ainda.")

# ==========================================
# 6. ABA RESTAURADA: PERFIL DETALHADO E PARCEIROS
# ==========================================
with aba_perfil:
    st.header("👤 Perfil Detalhado do Jogador")
    conn = obter_conexao()
    
    # Puxa a lista de atletas cadastrados no banco para criar a caixinha de seleção
    query_atletas = "SELECT DISTINCT jogador FROM stats_jogadores ORDER BY jogador ASC"
    df_atletas = pd.read_sql_query(query_atletas, conn)
    
    if not df_atletas.empty:
        jogador_selecionado = st.selectbox("Selecione um atleta para analisar os dados individuais:", df_atletas["jogador"])
        
        if jogador_selecionado:
            col_esq, col_dir = st.columns(2)
            
            with col_esq:
                st.subheader("📅 Histórico de Partidas")
                query_historico = """
                    SELECT 
                        p.data as "Data",
                        p.local_jogo as "Local",
                        s.time as "Seu Time",
                        CASE WHEN s.time = p.campeao THEN '🏆 Campeão' ELSE '➖' END as "Resultado"
                    FROM stats_jogadores s
                    JOIN partidas p ON s.partida_id = p.id
                    WHERE s.jogador = %s
                    ORDER BY p.data DESC
                """
                df_historico = pd.read_sql_query(query_historico, conn, params=[jogador_selecionado])
                st.dataframe(df_historico, use_container_width=True, hide_index=True)
                
            with col_dir:
                st.subheader("🤝 Melhores Parceiros (Entrosamento)")
                query_parceiros = """
                    SELECT 
                        s2.jogador as "Parceiro", 
                        COUNT(s2.partida_id) as "Jogos Juntos", 
                        SUM(CASE WHEN s2.time = p.campeao THEN 1 ELSE 0 END) as "Títulos Juntos"
                    FROM stats_jogadores s1
                    JOIN stats_jogadores s2 ON s1.partida_id = s2.partida_id AND s1.time = s2.time
                    JOIN partidas p ON s1.partida_id = p.id
                    WHERE s1.jogador = %s AND s2.jogador != %s
                    GROUP BY s2.jogador
                """
                df_parceiros = pd.read_sql_query(query_parceiros, conn, params=[jogador_selecionado])
                
                if not df_parceiros.empty:
                    # Faz o cálculo matemático da porcentagem de vitórias juntos
                    df_parceiros["% Aproveitamento"] = (
                        (df_parceiros["Títulos Juntos"] / df_parceiros["Jogos Juntos"]) * 100
                    ).round(1)
                    
                    # Ordena do parceiro com quem ele mais ganhou títulos junto
                    df_parceiros = df_parceiros.sort_values(by="Títulos Juntos", ascending=False)
                    
                    # Formata a coluna adicionando o símbolo de porcentagem
                    df_parceiros["% Aproveitamento"] = df_parceiros["% Aproveitamento"].astype(str) + "%"
                    
                    st.dataframe(df_parceiros, use_container_width=True, hide_index=True)
                else:
                    st.info("Este jogador ainda não possui registros jogando no mesmo time com parceiros.")
    else:
        st.info("Nenhum dado encontrado para gerar perfis.")
        
    conn.close()