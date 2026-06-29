from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from deep_translator import GoogleTranslator
import os
from datetime import datetime

app = Flask(__name__)

# Configuração do banco de dados
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'dicionario.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================================
# MODELOS DO BANCO DE DADOS
# ==========================================

class Palavra(db.Model):
    """Tabela de palavras em português"""
    id = db.Column(db.Integer, primary_key=True)
    palavra = db.Column(db.String(100), unique=True, nullable=False, index=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    traducoes = db.relationship('Traducao', backref='palavra', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'palavra': self.palavra,
            'traducoes': {t.idioma: t.traducao for t in self.traducoes},
            'data_criacao': self.data_criacao.isoformat()
        }

class Traducao(db.Model):
    """Tabela de traduções"""
    id = db.Column(db.Integer, primary_key=True)
    palavra_id = db.Column(db.Integer, db.ForeignKey('palavra.id'), nullable=False)
    idioma = db.Column(db.String(10), nullable=False)  # en, es, fr, etc
    traducao = db.Column(db.String(200), nullable=False)
    
    # Garante que não haja duplicatas (mesma palavra + mesmo idioma)
    __table_args__ = (db.UniqueConstraint('palavra_id', 'idioma', name='_palavra_idioma_uc'),)

# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================

def traduzir_com_fallback(palavra_texto, idioma_alvo):
    """
    Tenta buscar no banco. Se não achar, consulta a API do Google.
    """
    # 1. Busca no banco de dados
    palavra_obj = Palavra.query.filter_by(palavra=palavra_texto).first()
    
    if palavra_obj:
        for trad in palavra_obj.traducoes:
            if trad.idioma == idioma_alvo:
                return {
                    "traducao": trad.traducao,
                    "fonte": "📚 Banco de Dados"
                }
    
    # 2. Se não achou, consulta a API do Google
    try:
        resultado = GoogleTranslator(source='pt', target=idioma_alvo).translate(palavra_texto)
        
        if resultado is None:
            return {"traducao": None, "fonte": "❌ Não foi possível traduzir"}
        
        # Salva automaticamente no banco!
        if not palavra_obj:
            palavra_obj = Palavra(palavra=palavra_texto)
            db.session.add(palavra_obj)
            db.session.flush()  # Para pegar o ID
        
        # Verifica se já existe tradução para este idioma
        trad_existente = Traducao.query.filter_by(
            palavra_id=palavra_obj.id, 
            idioma=idioma_alvo
        ).first()
        
        if trad_existente:
            trad_existente.traducao = resultado
        else:
            nova_traducao = Traducao(
                palavra_id=palavra_obj.id,
                idioma=idioma_alvo,
                traducao=resultado
            )
            db.session.add(nova_traducao)
        
        db.session.commit()
        
        return {
            "traducao": resultado,
            "fonte": "🌐 Google Translate (salvo no banco!)"
        }
    except Exception as e:
        db.session.rollback()
        return {"traducao": None, "fonte": f"❌ Erro na API: {str(e)}"}

# ==========================================
# ROTAS DO SITE
# ==========================================

@app.route('/')
def index():
    """Página principal"""
    palavras = Palavra.query.order_by(Palavra.palavra).all()
    return render_template('index.html', palavras=[p.palavra for p in palavras])

@app.route('/traduzir', methods=['POST'])
def traduzir():
    """Recebe a palavra e idioma do formulário"""
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
    palavra_texto = dados.get('palavra', '').strip()
    idioma = dados.get('idioma', '').strip()
    traducao_texto = dados.get('traducao', '').strip()
    
    if not all([palavra_texto, idioma, traducao_texto]):
        return jsonify({"erro": "Preencha todos os campos!"})
    
    try:
        # Busca ou cria a palavra
        palavra_obj = Palavra.query.filter_by(palavra=palavra_texto).first()
        if not palavra_obj:
            palavra_obj = Palavra(palavra=palavra_texto)
            db.session.add(palavra_obj)
            db.session.flush()
        
        # Verifica se já existe tradução
        trad_existente = Traducao.query.filter_by(
            palavra_id=palavra_obj.id, 
            idioma=idioma
        ).first()
        
        if trad_existente:
            trad_existente.traducao = traducao_texto
        else:
            nova_traducao = Traducao(
                palavra_id=palavra_obj.id,
                idioma=idioma,
                traducao=traducao_texto
            )
            db.session.add(nova_traducao)
        
        db.session.commit()
        
        return jsonify({"sucesso": f"'{palavra_texto}' em {idioma} = '{traducao_texto}'"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"erro": f"Erro ao salvar: {str(e)}"}), 500

@app.route('/remover', methods=['POST'])
def remover():
    """Remove uma palavra ou tradução específica"""
    dados = request.get_json()
    palavra_texto = dados.get('palavra', '').strip()
    idioma = dados.get('idioma', '').strip()
    
    try:
        palavra_obj = Palavra.query.filter_by(palavra=palavra_texto).first()
        if not palavra_obj:
            return jsonify({"erro": "Palavra não encontrada"}), 404
        
        if not idioma:
            # Remove a palavra inteira
            db.session.delete(palavra_obj)
            db.session.commit()
            return jsonify({"sucesso": f"Palavra '{palavra_texto}' removida!"})
        else:
            # Remove apenas uma tradução
            trad = Traducao.query.filter_by(
                palavra_id=palavra_obj.id, 
                idioma=idioma
            ).first()
            if trad:
                db.session.delete(trad)
                db.session.commit()
                return jsonify({"sucesso": f"Tradução em {idioma} removida!"})
            else:
                return jsonify({"erro": "Tradução não encontrada"}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"erro": f"Erro ao remover: {str(e)}"}), 500

@app.route('/listar')
def listar():
    """Retorna todas as palavras do banco"""
    palavras = Palavra.query.order_by(Palavra.palavra).all()
    return jsonify([p.to_dict() for p in palavras])

@app.route('/api/palavras')
def api_palavras():
    """API para buscar palavras (autocomplete)"""
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])
    
    palavras = Palavra.query.filter(
        Palavra.palavra.ilike(f'%{query}%')
    ).limit(10).all()
    
    return jsonify([p.palavra for p in palavras])

# ==========================================
# INICIALIZAÇÃO DO BANCO
# ==========================================

def inicializar_banco():
    """Cria as tabelas e adiciona dados iniciais se vazio"""
    with app.app_context():
        db.create_all()
        
        # Se não houver palavras, adiciona algumas iniciais
        if Palavra.query.count() == 0:
            iniciais = [
                ("Olá", {"en": "Hello", "es": "Hola", "fr": "Bonjour"}),
                ("Obrigado", {"en": "Thank you", "es": "Gracias", "fr": "Merci"}),
                ("Bom dia", {"en": "Good morning", "es": "Buenos días", "fr": "Bonjour"}),
            ]
            
            for palavra_pt, traducoes in iniciais:
                p = Palavra(palavra=palavra_pt)
                db.session.add(p)
                db.session.flush()
                
                for idioma, trad in traducoes.items():
                    t = Traducao(palavra_id=p.id, idioma=idioma, traducao=trad)
                    db.session.add(t)
            
            db.session.commit()
            print("✅ Banco de dados inicializado com dados padrão!")

if __name__ == '__main__':
    inicializar_banco()
    app.run(debug=True, port=5000)