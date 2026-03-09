import streamlit as st
import pandas as pd
import psycopg2
from datetime import date

# --- FUNÇÃO DE CONEXÃO AO NEON ---
def obter_conexao():
    return psycopg2.connect(st.secrets["DATABASE_URL"])

# --- 1. CONFIGURAÇÃO DO BANCO DE DADOS ---
def init_db():
    conn = obter_conexao()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS partidas
                 (id SERIAL PRIMARY KEY, data DATE, campeao VARCHAR(50), 
                 pontos_azul INTEGER, pontos_vermelho INTEGER, pontos_preto INTEGER)''')
    
    # Criamos a tabela já com a nova coluna, caso seja um banco do zero
    c.execute('''CREATE TABLE IF NOT EXISTS stats_jogadores
                 (partida_id INTEGER, jogador VARCHAR(100), time VARCHAR(50), gols INTEGER, assistencias INTEGER DEFAULT 0,
                 FOREIGN KEY(partida_id) REFERENCES partidas(id))''')
                 
    # O Pulo do gato: Atualiza a tabela existente no Neon adicionando a coluna de assistências sem apagar nada
    c.execute("ALTER TABLE stats_jogadores ADD COLUMN IF NOT EXISTS assistencias INTEGER DEFAULT 0")
    
    conn.commit()
    conn.close()

init_db()

# --- 2. TÍTULO E LAYOUT ---
st.set_page_config(page_title="Stats Futebol", page_icon="⚽", layout="wide")
st.title("⚽ Estatísticas do Futebol Semanal")
st.write("Acompanhe o desempenho, artilharia, assistências e títulos.")

# ==============================================================================
#                               BARRA LATERAL (ÁREA RESTRITA)
# ==============================================================================

if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False

st.sidebar.header("🔐 Acesso Administrativo")

if not st.session_state['autenticado']:
    senha_digitada = st.sidebar.text_input("Digite a senha para editar", type="password")
    if st.sidebar.button("Entrar"):
        if senha_digitada == st.secrets["SENHA_ADMIN"]:
            st.session_state['autenticado'] = True
            st.rerun()
        else:
            st.sidebar.error("Senha incorreta!")

else:
    if st.sidebar.button("Sair / Bloquear"):
        st.session_state['autenticado'] = False
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.header("📝 Nova Rodada")

    # --- 3. ÁREA DE CADASTRO ---
    with st.sidebar.form("form_rodada"):
        data_jogo = st.date_input("Data do Jogo", date.today())
        
        st.subheader("Placar Final (Pontos)")
        pts_azul = st.number_input("Pontos Azul", min_value=0, step=1)
        pts_vermelho = st.number_input("Pontos Vermelho", min_value=0, step=1)
        pts_preto = st.number_input("Pontos Preto", min_value=0, step=1)
        
        campeao = st.selectbox("Time Campeão da Rodada", ["Azul", "Vermelho", "Preto", "Empate/Nenhum"])
        
        st.markdown("---")
        st.subheader("Desempenho Individual")
        st.caption("Formato: Nome, Time, Gols, Assistências. (Um por linha)") # Texto atualizado
        
        dados_brutos = st.text_area("Dados dos Jogadores (Ex: João, Azul, 2, 1)") # Exemplo atualizado
        
        enviar = st.form_submit_button("Salvar Rodada")

    if enviar and dados_brutos:
        conn = obter_conexao()
        c = conn.cursor()
        c.execute("INSERT INTO partidas (data, campeao, pontos_azul, pontos_vermelho, pontos_preto) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                  (data_jogo, campeao, pts_azul, pts_vermelho, pts_preto))
        partida_id = c.fetchone()[0] 
        
        linhas = dados_brutos.split('\n')
        for linha in linhas:
            if ',' in linha:
                partes = [p.strip() for p in linha.split(',')]
                if len(partes) >= 3:
                    nome = partes[0]
                    time = partes[1]
                    gols = int(partes[2])
                    # Se esquecer a assistência, assume 0
                    assistencias = int(partes[3]) if len(partes) >= 4 else 0 
                    
                    c.execute("INSERT INTO stats_jogadores (partida_id, jogador, time, gols, assistencias) VALUES (%s, %s, %s, %s, %s)",
                              (partida_id, nome, time, gols, assistencias))
        conn.commit()
        conn.close()
        st.sidebar.success("Dados salvos com sucesso!")
        st.rerun()

    # --- 4. ÁREA DE EDIÇÃO/CORREÇÃO ---
    st.sidebar.markdown("---")
    st.sidebar.header("✏️ Corrigir Estatísticas")
    conn_edit = obter_conexao()
    df_partidas_edit = pd.read_sql_query("SELECT id, data, campeao FROM partidas ORDER BY data DESC", conn_edit)
    conn_edit.close()

    if not df_partidas_edit.empty:
        opcoes_edit = df_partidas_edit.apply(lambda x: f"ID: {x['id']} | {x['data']} | {x['campeao']}", axis=1)
        escolha_edit = st.sidebar.selectbox("Selecione a Partida para Editar", options=opcoes_edit.values)
        
        if escolha_edit:
            id_partida_edit = int(escolha_edit.split("|")[0].replace("ID:", "").strip())
            conn_edit = obter_conexao()
            # Adicionado a coluna de assistências na busca
            query_jogadores = "SELECT jogador, time, gols, assistencias FROM stats_jogadores WHERE partida_id = %s"
            df_jogadores_edit = pd.read_sql_query(query_jogadores, conn_edit, params=(id_partida_edit,))
            conn_edit.close()

            st.sidebar.write("Faça as alterações na tabela abaixo:")
            df_editado = st.sidebar.data_editor(
                df_jogadores_edit, 
                num_rows="dynamic",
                hide_index=True,
                key="editor_dados"
            )

            if st.sidebar.button("SALVAR CORREÇÃO"):
                conn_save = obter_conexao()
                c_save = conn_save.cursor()
                try:
                    c_save.execute("DELETE FROM stats_jogadores WHERE partida_id = %s", (id_partida_edit,))
                    for index, row in df_editado.iterrows():
                        if row['jogador'] and row['time']:
                            # Usamos row.get para garantir que não dê erro se a coluna vier vazia
                            assist = row.get('assistencias', 0)
                            if pd.isna(assist): assist = 0
                                
                            c_save.execute(
                                "INSERT INTO stats_jogadores (partida_id, jogador, time, gols, assistencias) VALUES (%s, %s, %s, %s, %s)",
                                (id_partida_edit, row['jogador'], row['time'], row['gols'], assist)
                            )
                    conn_save.commit()
                    st.sidebar.success("Correção realizada!")
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"Erro ao salvar: {e}")
                finally:
                    conn_save.close()

    # --- 5. ZONA DE PERIGO (EXCLUSÃO) ---
    st.sidebar.markdown("---")
    st.sidebar.header("⚠️ Zona de Perigo")
    conn_del = obter_conexao()
    df_del = pd.read_sql_query("SELECT id, data, campeao FROM partidas", conn_del)
    conn_del.close()

    if not df_del.empty:
        opcoes_del = df_del.apply(lambda x: f"ID: {x['id']} | Data: {x['data']} | Vencedor: {x['campeao']}", axis=1)
        escolha_del = st.sidebar.selectbox("Selecionar Rodada para Excluir", options=opcoes_del.values)
        
        if st.sidebar.button("EXCLUIR RODADA SELECIONADA"):
            id_para_apagar = int(escolha_del.split("|")[0].replace("ID:", "").strip())
            conn_del = obter_conexao()
            c_del = conn_del.cursor()
            c_del.execute("DELETE FROM stats_jogadores WHERE partida_id = %s", (id_para_apagar,))
            c_del.execute("DELETE FROM partidas WHERE id = %s", (id_para_apagar,))
            conn_del.commit()
            conn_del.close()
            st.sidebar.success("Rodada apagada!")
            st.rerun()

# ==============================================================================
#                               DASHBOARD PRINCIPAL
# ==============================================================================

conn = obter_conexao()
df_partidas = pd.read_sql_query("SELECT * FROM partidas", conn)
df_stats = pd.read_sql_query("SELECT * FROM stats_jogadores", conn)
conn.close()

if not df_stats.empty:
    df_partidas['data'] = pd.to_datetime(df_partidas['data'])
    df_partidas['periodo'] = df_partidas['data'].dt.to_period('M')

    df_completo = pd.merge(df_stats, df_partidas, left_on='partida_id', right_on='id')

    st.markdown("---")
    col_filtro, col_vazia = st.columns([1, 2])
    
    with col_filtro:
        lista_meses = sorted(df_completo['periodo'].unique().astype(str), reverse=True)
        opcoes = ["Geral (Todo o Período)"] + lista_meses
        escolha_periodo = st.selectbox("📅 Filtrar Ranking por:", opcoes)

    if escolha_periodo == "Geral (Todo o Período)":
        df_ativo = df_completo.copy()
        titulo_secao = "Classificação Geral 🏆"
    else:
        df_ativo = df_completo[df_completo['periodo'].astype(str) == escolha_periodo].copy()
        titulo_secao = f"Classificação de {escolha_periodo} 📅"

    if not df_ativo.empty:
        ranking_gols = df_ativo.groupby('jogador')['gols'].sum().sort_values(ascending=False).reset_index()
        ranking_assist = df_ativo.groupby('jogador')['assistencias'].sum().reset_index() # CÁLCULO DE ASSISTÊNCIAS
        
        df_vitorias = df_ativo[df_ativo['time'] == df_ativo['campeao']]
        ranking_titulos = df_vitorias['jogador'].value_counts().reset_index()
        ranking_titulos.columns = ['jogador', 'titulos']

        presenca = df_ativo['jogador'].value_counts().reset_index()
        presenca.columns = ['jogador', 'jogos']

        # Juntando todas as tabelas
        tabela_geral = pd.merge(ranking_gols, ranking_titulos, on='jogador', how='outer').fillna(0)
        tabela_geral = pd.merge(tabela_geral, presenca, on='jogador', how='outer').fillna(0)
        tabela_geral = pd.merge(tabela_geral, ranking_assist, on='jogador', how='outer').fillna(0)
        
        tabela_geral['titulos'] = tabela_geral['titulos'].astype(int)
        tabela_geral['gols'] = tabela_geral['gols'].astype(int)
        tabela_geral['assistencias'] = tabela_geral['assistencias'].astype(int)
        tabela_geral['jogos'] = tabela_geral['jogos'].astype(int)
        
        tabela_geral['media_gols'] = tabela_geral.apply(
            lambda x: round(x['gols'] / x['jogos'], 2) if x['jogos'] > 0 else 0, axis=1
        )
        
        # O desempate agora é: Títulos > Gols > Assistências > Menos Jogos
        tabela_geral = tabela_geral.sort_values(by=['titulos', 'gols', 'assistencias', 'jogos'], ascending=[False, False, False, True])
    else:
        tabela_geral = pd.DataFrame(columns=['jogador', 'titulos', 'gols', 'assistencias', 'jogos', 'media_gols'])

    st.header(titulo_secao)
    st.dataframe(
        tabela_geral, 
        use_container_width=True,
        column_config={
            "jogador": "Atleta",
            "titulos": st.column_config.NumberColumn("🏆 Títulos", format="%d"),
            "gols": st.column_config.NumberColumn("⚽ Gols", format="%d"),
            "assistencias": st.column_config.NumberColumn("👟 Assistências", format="%d"),
            "jogos": "Jogos",
            "media_gols": "Média"
        },
        hide_index=True
    )

    if not tabela_geral.empty:
        col1, col2 = st.columns(2)
        with col1:
            st.caption("Artilharia do Período")
            st.bar_chart(ranking_gols.set_index('jogador').head(5))
        with col2:
            st.caption("Maiores Garçons (Assistências)") # Gráfico novo substituindo o de títulos ou dividindo espaço
            st.bar_chart(ranking_assist.set_index('jogador').sort_values(by='assistencias', ascending=False).head(5))

    st.markdown("---")
    st.header("👤 Detalhes do Jogador")

    lista_jogadores = sorted(df_completo['jogador'].unique())
    if lista_jogadores:
        jogador_selecionado = st.selectbox("Selecione um Atleta para ver a evolução:", lista_jogadores)

        df_jogador = df_completo[df_completo['jogador'] == jogador_selecionado].copy()
        df_jogador = df_jogador.sort_values(by='data')

        col_metrics1, col_metrics2, col_metrics3, col_metrics4 = st.columns(4)
        total_gols = df_jogador['gols'].sum()
        total_assistencias = df_jogador['assistencias'].sum()
        total_jogos = len(df_jogador)
        total_vitorias = len(df_jogador[df_jogador['time'] == df_jogador['campeao']])

        col_metrics1.metric("Gols (Carreira)", int(total_gols))
        col_metrics2.metric("Assistências", int(total_assistencias))
        col_metrics3.metric("Jogos Disputados", int(total_jogos))
        col_metrics4.metric("Títulos", int(total_vitorias))
        
        with st.expander(f"Ver histórico de partidas de {jogador_selecionado}"):
            st.dataframe(
                df_jogador[['data', 'time', 'gols', 'assistencias', 'campeao']].sort_values(by='data', ascending=False),
                use_container_width=True,
                column_config={
                    "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                    "time": "Time que Jogou",
                    "gols": "Gols",
                    "assistencias": "Assist.",
                    "campeao": "Vencedor"
                }
            )

    st.markdown("---")
    st.header("📜 Histórico Geral de Partidas")
    df_display_partidas = df_partidas.copy()
    df_display_partidas['data'] = df_display_partidas['data'].dt.strftime('%d/%m/%Y')
    st.dataframe(df_display_partidas[['id', 'data', 'campeao', 'pontos_azul', 'pontos_vermelho', 'pontos_preto']].sort_values(by='id', ascending=False), use_container_width=True)

else:
    st.info("Ainda não há dados cadastrados.")