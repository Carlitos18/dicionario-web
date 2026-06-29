from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from deep_translator import GoogleTranslator
import requests
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sua_chave_secreta_super_segura_aqui'

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'dicionario.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ==========================================
# MODELOS DO BANCO DE DADOS
# ==========================================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    palavras = db.relationship('Palavra', backref='dono', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Palavra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    palavra = db.Column(db.String(100), nullable=False, index=True)
    nota_gramatical = db.Column(db.Text, nullable=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    traducoes = db.relationship('Traducao', backref='palavra_obj', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'palavra': self.palavra,
            'nota_gramatical': self.nota_gramatical,
            'traducoes': {t.idioma: t.traducao for t in self.traducoes}
        }

class Traducao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    palavra_id = db.Column(db.Integer, db.ForeignKey('palavra.id'), nullable=False)
    idioma = db.Column(db.String(10), nullable=False)
    traducao = db.Column(db.String(200), nullable=False)
    __table_args__ = (db.UniqueConstraint('palavra_id', 'idioma', name='_palavra_idioma_uc'),)

# ==========================================
# FLASK-LOGIN
# ==========================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ==========================================
# BASE DE DADOS DE GRAMÁTICA
# ==========================================

GRAMMAR_RULES = [
    {
        "idioma": "en",
        "titulo": "🇺🇸 Make vs Do",
        "resumo": "Diferença fundamental entre criar e agir.",
        "conteudo": "<p><strong>Make</strong> é usado para criar, construir ou produzir algo:</p><ul><li>Make a cake (fazer um bolo)</li><li>Make a decision (tomar uma decisão)</li><li>Make money (ganhar dinheiro)</li></ul><p style='margin-top:10px'><strong>Do</strong> é usado para ações e atividades:</p><ul><li>Do homework (fazer lição de casa)</li><li>Do exercise (fazer exercício)</li><li>Do your best (fazer o seu melhor)</li></ul>"
    },
    {
        "idioma": "en",
        "titulo": "🇺🇸 Present Perfect",
        "resumo": "Ações passadas com relevância no presente.",
        "conteudo": "<p>Usado para ações que começaram no passado e continuam no presente.</p><p style='margin-top:10px'><strong>Estrutura:</strong> Sujeito + have/has + verbo no particípio</p><ul><li>I <strong>have studied</strong> English for 5 years.</li><li>She <strong>has visited</strong> Paris twice.</li><li>They <strong>have just finished</strong> the project.</li></ul>"
    },
    {
        "idioma": "en",
        "titulo": "🇸 Since vs For",
        "resumo": "Como falar de duração no tempo.",
        "conteudo": "<p>Ambos são usados com o Present Perfect:</p><ul><li><strong>Since</strong> (Desde): Indica o ponto de início. (Since 2010, Since Monday)</li><li><strong>For</strong> (Por/Durante): Indica o período total. (For 5 years, For 2 hours)</li></ul><p><strong>Exemplo:</strong> I have lived here <strong>since</strong> 2015. I have lived here <strong>for</strong> 9 years.</p>"
    },
    {
        "idioma": "es",
        "titulo": "🇪🇸 Ser vs Estar",
        "resumo": "O dilema clássico do espanhol.",
        "conteudo": "<p><strong>Ser</strong> para características permanentes:</p><ul><li>Soy alto (sou alto)</li><li>Es médico (é médico)</li><li>Son amigos (são amigos)</li></ul><p style='margin-top:10px'><strong>Estar</strong> para estados temporários e localização:</p><ul><li>Estoy cansado (estou cansado)</li><li>Está en casa (está em casa)</li><li>Estamos felizes (estamos felizes)</li></ul>"
    },
    {
        "idioma": "es",
        "titulo": "🇪 Por vs Para",
        "resumo": "Preposições que confundem todos.",
        "conteudo": "<p><strong>Para</strong> indica destino, propósito, prazo:</p><ul><li>Este regalo es <strong>para</strong> ti.</li><li>Estudio <strong>para</strong> aprender.</li><li>La tarea es <strong>para</strong> mañana.</li></ul><p style='margin-top:10px'><strong>Por</strong> indica causa, motivo, troca:</p><ul><li>Gracias <strong>por</strong> la ayuda.</li><li>Caminamos <strong>por</strong> el parque.</li><li>Te cambio mi manzana <strong>por</strong> tu naranja.</li></ul>"
    },
    {
        "idioma": "fr",
        "titulo": "🇫🇷 Artigos Definidos",
        "resumo": "Como usar 'O' e 'A' em francês.",
        "conteudo": "<ul><li><strong>le</strong> (masculino singular): le livre (o livro)</li><li><strong>la</strong> (feminino singular): la maison (a casa)</li><li><strong>l'</strong> (antes de vogal): l'ami (o amigo)</li><li><strong>les</strong> (plural): les enfants (as crianças)</li></ul>"
    },
    {
        "idioma": "fr",
        "titulo": "🇫🇷 Être vs Avoir",
        "resumo": "Os dois pilares do francês.",
        "conteudo": "<p><strong>Être</strong> (Ser/Estar) para descrições e localização:</p><ul><li>Je <strong>suis</strong> content.</li><li>Il <strong>est</strong> professeur.</li></ul><p style='margin-top:10px'><strong>Avoir</strong> (Ter) para posse, idade e sensações:</p><ul><li>J'<strong>ai</strong> un chat.</li><li>J'<strong>ai</strong> 25 ans.</li><li>J'<strong>ai</strong> faim.</li></ul>"
    },
    {
        "idioma": "pt",
        "titulo": "🇷 Crase: A Regra de Ouro",
        "resumo": "Nunca mais erre o uso da crase.",
        "conteudo": "<p>Substitua a palavra feminina por uma masculina. Se aparecer <strong>'ao'</strong>, então tem crase:</p><ul><li>Vou <strong>à</strong> escola -> Vou <strong>ao</strong> colégio. (Tem crase!)</li><li>Vou <strong>a</strong> pé -> Vou <strong>a</strong> cavalo. (Não tem crase!)</li><li>Entreguei <strong>à</strong> diretora -> Entreguei <strong>ao</strong> diretor. (Tem crase!)</li></ul>"
    },
    {
        "idioma": "pt",
        "titulo": "🇧🇷 Mas vs Mais",
        "resumo": "Oposição vs Quantidade.",
        "conteudo": "<p><strong>Mas</strong> indica oposição (pode ser trocado por 'porém'):</p><ul><li>Estudei muito, <strong>mas</strong> não passei.</li><li>Ele é rico, <strong>mas</strong> é infeliz.</li></ul><p style='margin-top:10px'><strong>Mais</strong> indica quantidade (oposto de 'menos'):</p><ul><li>Eu quero <strong>mais</strong> café.</li><li>Ela é a <strong>mais</strong> inteligente da turma.</li></ul>"
    }
]

# ==========================================
# CORREÇÃO GRAMATICAL (LanguageTool)
# ==========================================

def corrigir_gramatica(texto, idioma='pt-BR'):
    try:
        url = "https://api.languagetool.org/v2/check"
        dados = {'text': texto, 'language': idioma}
        resposta = requests.post(url, data=dados, timeout=5)
        resultado = resposta.json()
        
        texto_corrigido = texto
        matches = resultado.get('matches', [])
        matches.sort(key=lambda x: x['offset'], reverse=True)
        
        for match in matches:
            offset = match['offset']
            length = match['length']
            replacements = match.get('replacements', [])
            if replacements:
                texto_corrigido = texto_corrigido[:offset] + replacements[0]['value'] + texto_corrigido[offset + length:]
        
        return {
            'texto_corrigido': texto_corrigido,
            'erros_encontrados': len(matches),
            'sugestoes': [
                {
                    'mensagem': m.get('message', ''),
                    'contexto': m.get('context', {}).get('text', ''),
                    'replacements': [r['value'] for r in m.get('replacements', [])[:3]]
                }
                for m in matches[:5]
            ]
        }
    except Exception as e:
        return {'texto_corrigido': texto, 'erros_encontrados': 0, 'erro': f'Erro na API: {str(e)}'}

# ==========================================
# TRADUÇÃO
# ==========================================

def traduzir_com_fallback(palavra_texto, idioma_alvo):
    if current_user.is_authenticated:
        palavra_obj = Palavra.query.filter_by(palavra=palavra_texto, user_id=current_user.id).first()
        if palavra_obj:
            for trad in palavra_obj.traducoes:
                if trad.idioma == idioma_alvo:
                    return {"traducao": trad.traducao, "fonte": " Seu Dicionário"}
    
    try:
        resultado = GoogleTranslator(source='pt', target=idioma_alvo).translate(palavra_texto)
        if not resultado:
            return {"traducao": None, "fonte": "❌ Não foi possível traduzir"}
        
        if current_user.is_authenticated:
            if not palavra_obj:
                palavra_obj = Palavra(palavra=palavra_texto, user_id=current_user.id)
                db.session.add(palavra_obj)
                db.session.flush()
            
            trad_existente = Traducao.query.filter_by(palavra_id=palavra_obj.id, idioma=idioma_alvo).first()
            if trad_existente:
                trad_existente.traducao = resultado
            else:
                db.session.add(Traducao(palavra_id=palavra_obj.id, idioma=idioma_alvo, traducao=resultado))
            
            db.session.commit()
            return {"traducao": resultado, "fonte": "🌐 Google Translate (salvo!)"}
        else:
            return {"traducao": resultado, "fonte": "🌐 Google Translate (faça login para salvar!)"}
            
    except Exception as e:
        return {"traducao": None, "fonte": f"❌ Erro na API: {str(e)}"}

# ==========================================
# ROTAS DE AUTENTICAÇÃO
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        dados = request.get_json()
        username = dados.get('username', '').strip()
        password = dados.get('password', '').strip()
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return jsonify({"sucesso": True, "redirect": "/"})
        return jsonify({"erro": "Usuário ou senha incorretos"}), 401
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    dados = request.get_json()
    username = dados.get('username', '').strip()
    password = dados.get('password', '').strip()
    if not username or not password:
        return jsonify({"erro": "Preencha todos os campos"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"erro": "Este nome de usuário já existe"}), 400
    novo_user = User(username=username)
    novo_user.set_password(password)
    db.session.add(novo_user)
    db.session.commit()
    login_user(novo_user)
    return jsonify({"sucesso": True, "redirect": "/"})

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return jsonify({"sucesso": True})

# ==========================================
# ROTAS DO APLICATIVO
# ==========================================

@app.route('/')
def index():
    if current_user.is_authenticated:
        palavras = Palavra.query.filter_by(user_id=current_user.id).order_by(Palavra.palavra).all()
        return render_template('index.html', palavras=[p.palavra for p in palavras])
    return render_template('index.html', palavras=[])

@app.route('/traduzir', methods=['POST'])
def traduzir():
    dados = request.get_json()
    palavra = dados.get('palavra', '').strip()
    idioma = dados.get('idioma', '').strip()
    if not palavra or not idioma:
        return jsonify({"erro": "Preencha todos os campos"}), 400
    return jsonify(traduzir_com_fallback(palavra, idioma))

@app.route('/adicionar', methods=['POST'])
@login_required
def adicionar():
    dados = request.get_json()
    palavra_texto = dados.get('palavra', '').strip()
    idioma = dados.get('idioma', '').strip()
    traducao_texto = dados.get('traducao', '').strip()
    nota_gramatical = dados.get('nota', '').strip()
    if not all([palavra_texto, idioma, traducao_texto]):
        return jsonify({"erro": "Preencha todos os campos"}), 400
    palavra_obj = Palavra.query.filter_by(palavra=palavra_texto, user_id=current_user.id).first()
    if not palavra_obj:
        palavra_obj = Palavra(palavra=palavra_texto, user_id=current_user.id, nota_gramatical=nota_gramatical)
        db.session.add(palavra_obj)
        db.session.flush()
    else:
        if nota_gramatical:
            palavra_obj.nota_gramatical = nota_gramatical
    trad_existente = Traducao.query.filter_by(palavra_id=palavra_obj.id, idioma=idioma).first()
    if trad_existente:
        trad_existente.traducao = traducao_texto
    else:
        db.session.add(Traducao(palavra_id=palavra_obj.id, idioma=idioma, traducao=traducao_texto))
    db.session.commit()
    return jsonify({"sucesso": f"'{palavra_texto}' adicionado!"})

@app.route('/corrigir', methods=['POST'])
def corrigir():
    dados = request.get_json()
    texto = dados.get('texto', '').strip()
    idioma = dados.get('idioma', 'pt-BR')
    if not texto:
        return jsonify({"erro": "Digite um texto para corrigir"}), 400
    resultado = corrigir_gramatica(texto, idioma)
    return jsonify(resultado)

@app.route('/remover', methods=['POST'])
@login_required
def remover():
    dados = request.get_json()
    palavra_texto = dados.get('palavra', '').strip()
    palavra_obj = Palavra.query.filter_by(palavra=palavra_texto, user_id=current_user.id).first()
    if palavra_obj:
        db.session.delete(palavra_obj)
        db.session.commit()
        return jsonify({"sucesso": "Removido!"})
    return jsonify({"erro": "Não encontrado"}), 404

@app.route('/listar')
@login_required
def listar():
    palavras = Palavra.query.filter_by(user_id=current_user.id).order_by(Palavra.palavra).all()
    return jsonify([p.to_dict() for p in palavras])

@app.route('/api/palavras')
@login_required
def api_palavras():
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])
    palavras = Palavra.query.filter(
        Palavra.user_id == current_user.id, 
        Palavra.palavra.ilike(f'%{query}%')
    ).limit(10).all()
    return jsonify([p.palavra for p in palavras])

@app.route('/api/gramatica')
def api_gramatica():
    return jsonify(GRAMMAR_RULES)

# ==========================================
# INICIALIZAÇÃO
# ==========================================

def inicializar_banco():
    with app.app_context():
        db.create_all()
        print("✅ Banco de dados pronto!")

inicializar_banco()

if __name__ == '__main__':
    app.run(debug=True, port=5000)