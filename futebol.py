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
    
    c.execute('''CREATE TABLE IF NOT EXISTS stats_jogadores
                 (partida_id INTEGER, jogador VARCHAR(100), time VARCHAR(50), gols INTEGER, assistencias INTEGER DEFAULT 0,
                 FOREIGN KEY(partida_id) REFERENCES partidas(id))''')
                 
    # Garante que a coluna de assistências exista mesmo em bancos antigos
    c.execute("ALTER TABLE stats_jogadores ADD COLUMN IF NOT EXISTS assistencias INTEGER DEFAULT 0")
    
    conn.commit()
    conn.close()

init_db()

# --- 2. TÍTULO E LAYOUT PRINCIPAL ---
st.set_page_config(page_title="Stats Futebol", page_icon="⚽", layout="wide")
st.title("⚽ Estatísticas do Futebol Semanal")
st.write("Acompanhe o desempenho, artilharia, assistências e títulos.")

# ==============================================================================
#                               BARRA LATERAL (ÁREA RESTRITA)
# ==============================================================================

# Cria a variável de sessão para o login se ela não existir
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False

st.sidebar.header("🔐 Acesso Administrativo")

# --- SE NÃO ESTIVER LOGADO ---
if not st.session_state['autenticado']:
    senha_digitada = st.sidebar.text_input("Digite a senha para editar", type="password")
    if st.sidebar.button("Entrar"):
        if senha_digitada == st.secrets["SENHA_ADMIN"]:
            st.session_state['autenticado'] = True
            st.rerun()
        else:
            st.sidebar.error("Senha incorreta!")

# --- SE ESTIVER LOGADO ---
else:
    if st.sidebar.button("Sair / Bloquear"):
        st.session_state['autenticado'] = False
        st.rerun()

    st.sidebar.markdown("---")
    
    # Menu de navegação da barra lateral
    opcao_admin = st.sidebar.radio("O que deseja fazer?", ["Nova Rodada", "Ajuste por Atleta", "Editar Rodada Completa", "Excluir Rodada"])

    st.sidebar.markdown("---")

    # === OPÇÃO 1: NOVA RODADA ===
    if opcao_admin == "Nova Rodada":
        st.sidebar.subheader("📝 Nova Rodada")
        with st.sidebar.form("form_rodada"):
            data_jogo = st.date_input("Data do Jogo", date.today())
            
            st.write("Placar Final (Pontos)")
            pts_azul = st.number_input("Pontos Azul", min_value=0, step=1)
            pts_vermelho = st.number_input("Pontos Vermelho", min_value=0, step=1)
            pts_preto = st.number_input("Pontos Preto", min_value=0, step=1)
            
            campeao = st.selectbox("Time Campeão", ["Azul", "Vermelho", "Preto", "Empate/Nenhum"])
            
            st.write("Desempenho Individual")
            st.caption("Formato: Nome, Time, Gols, Assistências. (Um por linha)")
            dados_brutos = st.text_area("Dados dos Jogadores (Ex: João, Azul, 2, 1)")
            
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
                        assist = int(partes[3]) if len(partes) >= 4 else 0 
                        
                        c.execute("INSERT INTO stats_jogadores (partida_id, jogador, time, gols, assistencias) VALUES (%s, %s, %s, %s, %s)",
                                  (partida_id, nome, time, gols, assist))
            conn.commit()
            conn.close()
            st.sidebar.success("Rodada salva com sucesso!")
            st.rerun()

    # === OPÇÃO 2: AJUSTE POR ATLETA (CIRÚRGICO) ===
    elif opcao_admin == "Ajuste por Atleta":
        st.sidebar.subheader("🎯 Ajuste Cirúrgico")
        conn = obter_conexao()
        jogadores_unicos = pd.read_sql_query("SELECT DISTINCT jogador FROM stats_jogadores ORDER BY jogador", conn)['jogador'].tolist()
        conn.close()

        if jogadores_unicos:
            atleta_sel = st.sidebar.selectbox("Selecione o Atleta", jogadores_unicos)

            if atleta_sel:
                conn = obter_conexao()
                query = """
                    SELECT s.partida_id, p.data, s.time, s.gols, s.assistencias
                    FROM stats_jogadores s
                    JOIN partidas p ON s.partida_id = p.id
                    WHERE s.jogador = %s
                    ORDER BY p.data DESC
                """
                df_hist_atleta = pd.read_sql_query(query, conn, params=(atleta_sel,))
                conn.close()

                st.sidebar.write(f"Editando histórico de: **{atleta_sel}**")
                st.sidebar.caption("Altere os gols e assistências abaixo:")
                
                df_ajustado = st.sidebar.data_editor(
                    df_hist_atleta,
                    hide_index=True,
                    disabled=["partida_id", "data", "time"], # Impede de mexer na data e time por engano
                    key="editor_individual"
                )

                if st.sidebar.button("Confirmar Alteração"):
                    conn = obter_conexao()
                    c = conn.cursor()
                    try:
                        for index, row in df_ajustado.iterrows():
                            # Usa get e trata valores nulos/NaN para evitar erros
                            gols_edit = int(row.get('gols', 0)) if not pd.isna(row.get('gols')) else 0
                            assist_edit = int(row.get('assistencias', 0)) if not pd.isna(row.get('assistencias')) else 0
                            
                            c.execute("""
                                UPDATE stats_jogadores 
                                SET gols = %s, assistencias = %s 
                                WHERE partida_id = %s AND jogador = %s
                            """, (gols_edit, assist_edit, int(row['partida_id']), atleta_sel))
                        
                        conn.commit()
                        st.sidebar.success(f"Dados atualizados!")
                        st.rerun()
                    except Exception as e:
                        st.sidebar.error(f"Erro: {e}")
                    finally:
                        conn.close()
        else:
            st.sidebar.info("Nenhum jogador cadastrado ainda.")

    # === OPÇÃO 3: EDITAR RODADA COMPLETA ===
    elif opcao_admin == "Editar Rodada Completa":
        st.sidebar.subheader("✏️ Corrigir Rodada")
        conn_edit = obter_conexao()
        df_partidas_edit = pd.read_sql_query("SELECT id, data, campeao FROM partidas ORDER BY data DESC", conn_edit)
        conn_edit.close()

        if not df_partidas_edit.empty:
            opcoes_edit = df_partidas_edit.apply(lambda x: f"ID: {x['id']} | {x['data']} | {x['campeao']}", axis=1)
            escolha_edit = st.sidebar.selectbox("Selecione a Partida", options=opcoes_edit.values)
            
            if escolha_edit:
                id_partida_edit = int(escolha_edit.split("|")[0].replace("ID:", "").strip())
                conn_edit = obter_conexao()
                query_jogadores = "SELECT jogador, time, gols, assistencias FROM stats_jogadores WHERE partida_id = %s"
                df_jogadores_edit = pd.read_sql_query(query_jogadores, conn_edit, params=(id_partida_edit,))
                conn_edit.close()

                st.sidebar.write("Faça as alterações na tabela abaixo:")
                df_editado = st.sidebar.data_editor(
                    df_jogadores_edit, 
                    num_rows="dynamic",
                    hide_index=True,
                    key="editor_dados_rodada"
                )

                if st.sidebar.button("Salvar Correção"):
                    conn_save = obter_conexao()
                    c_save = conn_save.cursor()
                    try:
                        # Apaga o antigo e insere o novo para garantir integridade caso adicione nova linha
                        c_save.execute("DELETE FROM stats_jogadores WHERE partida_id = %s", (id_partida_edit,))
                        for index, row in df_editado.iterrows():
                            if row['jogador'] and row['time']:
                                assist = int(row.get('assistencias', 0)) if not pd.isna(row.get('assistencias')) else 0
                                gols = int(row.get('gols', 0)) if not pd.isna(row.get('gols')) else 0
                                
                                c_save.execute(
                                    "INSERT INTO stats_jogadores (partida_id, jogador, time, gols, assistencias) VALUES (%s, %s, %s, %s, %s)",
                                    (id_partida_edit, row['jogador'], row['time'], gols, assist)
                                )
                        conn_save.commit()
                        st.sidebar.success("Rodada atualizada!")
                        st.rerun()
                    except Exception as e:
                        st.sidebar.error(f"Erro ao salvar: {e}")
                    finally:
                        conn_save.close()

    # === OPÇÃO 4: EXCLUIR RODADA ===
    elif opcao_admin == "Excluir Rodada":
        st.sidebar.subheader("⚠️ Excluir Rodada")
        conn_del = obter_conexao()
        df_del = pd.read_sql_query("SELECT id, data, campeao FROM partidas ORDER BY data DESC", conn_del)
        conn_del.close()

        if not df_del.empty:
            opcoes_del = df_del.apply(lambda x: f"ID: {x['id']} | Data: {x['data']} | Vencedor: {x['campeao']}", axis=1)
            escolha_del = st.sidebar.selectbox("Selecionar Partida", options=opcoes_del.values)
            
            if st.sidebar.button("Excluir Definitivamente"):
                id_para_apagar = int(escolha_del.split("|")[0].replace("ID:", "").strip())
                conn_del = obter_conexao()
                c_del = conn_del.cursor()
                c_del.execute("DELETE FROM stats_jogadores WHERE partida_id = %s", (id_para_apagar,))
                c_del.execute("DELETE FROM partidas WHERE id = %s", (id_para_apagar,))
                conn_del.commit()
                conn_del.close()
                st.sidebar.success("Partida apagada!")
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
        ranking_assist = df_ativo.groupby('jogador')['assistencias'].sum().reset_index()
        
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
        
        # Desempate: Títulos > Gols > Assistências > Menos Jogos
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
            st.caption("Maiores Garçons (Assistências)")
            st.bar_chart(ranking_assist.set_index('jogador').sort_values(by='assistencias', ascending=False).head(5))

    # --- 5. DETALHES DO JOGADOR ---
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
            # 1. Adicionamos o 'partida_id' na busca (ele será usado no filtro dos companheiros)
            df_historico = df_jogador[['partida_id', 'data', 'time', 'gols', 'assistencias', 'campeao']].sort_values(by='data', ascending=False).copy()
            
            df_historico['status'] = df_historico.apply(
                lambda x: '🏆 Campeão' if x['time'] == x['campeao'] else '➖', axis=1
            )
            
            def destacar_campeao(row):
                if row['time'] == row['campeao']:
                    return ['background-color: rgba(46, 204, 113, 0.2)'] * len(row)
                return [''] * len(row)

            st.dataframe(
                df_historico.style.apply(destacar_campeao, axis=1),
                use_container_width=True,
                column_config={
                    "partida_id": None, # Mantemos o ID invisível para não poluir a tela
                    "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                    "time": "Time que Jogou",
                    "gols": "Gols",
                    "assistencias": "Assist.",
                    "campeao": "Vencedor da Rodada",
                    "status": "Resultado"
                }
            )

            # =========================================================
            # NOVA FUNCIONALIDADE: COMPANHEIROS DE EQUIPE DO DIA
            # =========================================================
            st.markdown("---")
            st.subheader("🤝 Elenco da Partida")
            st.caption("Selecione uma data acima para ver quem formou o time com ele neste dia:")

            # Cria as opções para o Menu Suspenso (Ex: "15/04/2026 | Time Azul")
            opcoes_datas = df_historico.apply(
                lambda x: f"{x['data'].strftime('%d/%m/%Y')} | Time {x['time']} (ID:{x['partida_id']})", axis=1
            ).tolist()

            if opcoes_datas:
                escolha_partida = st.selectbox("Escolha a partida:", opcoes_datas, label_visibility="collapsed")
                
                # O código extrai o número do ID e a cor do time escolhidos no texto
                id_escolhido = int(escolha_partida.split("ID:")[1].replace(")", "").strip())
                time_escolhido = escolha_partida.split(" | Time ")[1].split(" (")[0].strip()

                # Filtra todo o banco de dados buscando apenas quem jogou na mesma data e no mesmo time
                df_elenco = df_completo[(df_completo['partida_id'] == id_escolhido) & (df_completo['time'] == time_escolhido)].copy()
                
                # Ordena para quem fez mais gols e assistências aparecer no topo
                df_elenco = df_elenco[['jogador', 'gols', 'assistencias']].sort_values(by=['gols', 'assistencias'], ascending=False)

                # Coloca um marcador "(Em foco)" no jogador que você está pesquisando
                df_elenco['jogador'] = df_elenco['jogador'].apply(lambda x: f"⭐ {x} (Em foco)" if x == jogador_selecionado else x)

                # Exibe a tabela do elenco
                st.dataframe(
                    df_elenco,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "jogador": "Atleta",
                        "gols": "⚽ Gols no dia",
                        "assistencias": "👟 Assist. no dia"
                    }
                )
    
            # =========================================================
            # FUNCIONALIDADE ATUALIZADA: ENTROSAMENTO E TÍTULOS JUNTOS
            # =========================================================
            st.markdown("---")
            st.subheader("👥 Melhores Entrosamentos")
            st.caption(f"Análise de parceria e vitórias de {jogador_selecionado}.")

            # 1. Selecionamos as partidas e times do jogador, incluindo quem foi o campeão
            partidas_foco = df_jogador[['partida_id', 'time', 'campeao']]

            # 2. Cruzamos com o banco geral para encontrar quem estava no mesmo time nessas datas
            df_parceiros = pd.merge(df_completo, partidas_foco, on=['partida_id', 'time'])

            # 3. Removemos o próprio jogador da lista de parceiros
            df_parceiros = df_parceiros[df_parceiros['jogador'] != jogador_selecionado]

            # 4. Marcamos as vitórias em conjunto (quando o time da dupla foi o campeão)
            # 'campeao_y' refere-se à coluna vinda do dataframe do jogador selecionado
            df_parceiros['ganharam_juntos'] = (df_parceiros['time'] == df_parceiros['campeao_y']).astype(int)

            # 5. Consolidamos o ranking por parceiro
            ranking_duplas = df_parceiros.groupby('jogador').agg(
                total_jogos=('partida_id', 'count'),
                total_vitorias=('ganharam_juntos', 'sum')
            ).reset_index()

            ranking_duplas.columns = ['Parceiro', 'Jogos Juntos', 'Títulos Juntos']
            
            # Ordenação prioritária por Títulos, depois por quantidade de jogos
            ranking_duplas = ranking_duplas.sort_values(by=['Títulos Juntos', 'Jogos Juntos'], ascending=False)

            if not ranking_duplas.empty:
                max_j = int(ranking_duplas['Jogos Juntos'].max())
                # Define o máximo para a barra de títulos (mínimo de 1 para evitar erro de escala)
                max_t = int(ranking_duplas['Títulos Juntos'].max()) if ranking_duplas['Títulos Juntos'].max() > 0 else 1
                
                st.dataframe(
                    ranking_duplas.head(10),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Parceiro": "Atleta",
                        "Jogos Juntos": st.column_config.ProgressColumn(
                            "Partidas no Time",
                            format="%d jogos",
                            min_value=0,
                            max_value=max_j
                        ),
                        "Títulos Juntos": st.column_config.ProgressColumn(
                            "Títulos em Dupla",
                            format="%d 🏆",
                            min_value=0,
                            max_value=max_t,
                            color="orange"
                        )
                    }
                )
            else:
                st.info("Ainda não há parcerias registradas para este jogador.")
    
    st.markdown("---")
    st.header("📜 Histórico Geral de Partidas")
    df_display_partidas = df_partidas.copy()
    df_display_partidas['data'] = df_display_partidas['data'].dt.strftime('%d/%m/%Y')
    st.dataframe(df_display_partidas[['id', 'data', 'campeao', 'pontos_azul', 'pontos_vermelho', 'pontos_preto']].sort_values(by='id', ascending=False), use_container_width=True)

else:
    st.info("Ainda não há dados cadastrados.")