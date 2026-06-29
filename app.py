from flask import Flask, render_template, request, jsonify
from deep_translator import GoogleTranslator
import json
import os

app = Flask(__name__)
translator = GoogleTranslator()

NOME_ARQUIVO = "meu_dicionario.json"

# ==========================================
# FUNÇÕES DE PERSISTÊNCIA (iguais às de antes)
# ==========================================
def carregar_dicionario():
    if os.path.exists(NOME_ARQUIVO):
        with open(NOME_ARQUIVO, 'r', encoding='utf-8') as arquivo:
            return json.load(arquivo)
    return {
        "Olá": {"en": "Hello", "es": "Hola"},
        "Obrigado": {"en": "Thank you", "es": "Gracias"}
    }

def salvar_dicionario(dicionario):
    with open(NOME_ARQUIVO, 'w', encoding='utf-8') as arquivo:
        json.dump(dicionario, arquivo, indent=4, ensure_ascii=False)

# Carrega o dicionário ao iniciar
traducoes = carregar_dicionario()

# ==========================================
# FUNÇÃO MÁGICA: TRADUZIR COM FALLBACK
# ==========================================
def traduzir_com_fallback(palavra, idioma_alvo):
    """
    Tenta buscar no dicionário local. Se não achar, 
    consulta a API do Google Translate automaticamente.
    """
    # 1. Tenta no dicionário local
    idiomas = traducoes.get(palavra)
    if idiomas and idioma_alvo in idiomas:
        return {
            "traducao": idiomas[idioma_alvo],
            "fonte": "📚 Dicionário Local"
        }
    
    # 2. Se não achou, consulta a API do Google
    try:
        # deep-translator já entende os códigos curtos (en, es, fr, etc)
        resultado = GoogleTranslator(source='pt', target=idioma_alvo).translate(palavra)
        
        if resultado is None:
            return {
                "traducao": None,
                "fonte": "❌ Não foi possível traduzir"
            }
        
        # Salva automaticamente no dicionário para próximas vezes!
        if palavra not in traducoes:
            traducoes[palavra] = {}
        traducoes[palavra][idioma_alvo] = resultado
        salvar_dicionario(traducoes)
        
        return {
            "traducao": resultado,
            "fonte": "🌐 Google Translate (salvo no dicionário!)"
        }
    except Exception as e:
        return {
            "traducao": None,
            "fonte": f"❌ Erro na API: {str(e)}"
        }


# ==========================================
# ROTAS DO SITE
# ==========================================

@app.route('/')
def index():
    """Página principal"""
    return render_template('index.html', palavras=list(traducoes.keys()))

@app.route('/traduzir', methods=['POST'])
def traduzir():
    """Recebe a palavra e idioma do formulário e retorna a tradução"""
    dados = request.get_json()
    palavra = dados.get('palavra', '').strip()
    idioma = dados.get('idioma', '').strip()
    
    if not palavra or not idioma:
        return jsonify({"erro": "Preencha todos os campos!"})
    
    resultado = traduzir_com_fallback(palavra, idioma)
    return jsonify(resultado)

@app.route('/adicionar', methods=['POST'])
def adicionar():
    """Adiciona uma tradução manualmente"""
    dados = request.get_json()
    palavra = dados.get('palavra', '').strip()
    idioma = dados.get('idioma', '').strip()
    traducao = dados.get('traducao', '').strip()
    
    if not all([palavra, idioma, traducao]):
        return jsonify({"erro": "Preencha todos os campos!"})
    
    if palavra not in traducoes:
        traducoes[palavra] = {}
    traducoes[palavra][idioma] = traducao
    salvar_dicionario(traducoes)
    
    return jsonify({"sucesso": f"'{palavra}' em {idioma} = '{traducao}'"})

@app.route('/listar')
def listar():
    """Retorna todas as palavras do dicionário"""
    return jsonify(traducoes)


if __name__ == '__main__':
    # debug=True recarrega o servidor automaticamente quando você muda o código
    app.run(debug=True, port=5000)