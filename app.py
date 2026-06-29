from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from deep_translator import GoogleTranslator
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sua_chave_secreta_super_segura_aqui' # Mude isso em produção!

# Configuração do banco de dados
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'dicionario.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Redireciona para /login se tentar acessar área restrita

# ==========================================
# MODELOS DO BANCO DE DADOS
# ==========================================

class User(UserMixin, db.Model):
    """Tabela de Usuários"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relação: um usuário tem muitas palavras
    palavras = db.relationship('Palavra', backref='dono', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Palavra(db.Model):
    """Tabela de palavras"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # DONO DA PALAVRA
    palavra = db.Column(db.String(100), nullable=False, index=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    traducoes = db.relationship('Traducao', backref='palavra_obj', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'palavra': self.palavra,
            'traducoes': {t.idioma: t.traducao for t in self.traducoes}
        }

class Traducao(db.Model):
    """Tabela de traduções"""
    id = db.Column(db.Integer, primary_key=True)
    palavra_id = db.Column(db.Integer, db.ForeignKey('palavra.id'), nullable=False)
    idioma = db.Column(db.String(10), nullable=False)
    traducao = db.Column(db.String(200), nullable=False)
    __table_args__ = (db.UniqueConstraint('palavra_id', 'idioma', name='_palavra_idioma_uc'),)

# ==========================================
# FLASK-LOGIN SETUP
# ==========================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ==========================================
# FUNÇÕES DE TRADUÇÃO
# ==========================================

def traduzir_com_fallback(palavra_texto, idioma_alvo):
    # Busca APENAS nas palavras do usuário atual
    palavra_obj = Palavra.query.filter_by(palavra=palavra_texto, user_id=current_user.id).first()
    
    if palavra_obj:
        for trad in palavra_obj.traducoes:
            if trad.idioma == idioma_alvo:
                return {"traducao": trad.traducao, "fonte": "📚 Seu Dicionário"}
    
    try:
        resultado = GoogleTranslator(source='pt', target=idioma_alvo).translate(palavra_texto)
        if not resultado:
            return {"traducao": None, "fonte": "❌ Não foi possível traduzir"}
        
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
    except Exception as e:
        db.session.rollback()
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
# ROTAS DO APLICATIVO (PROTEGIDAS)
# ==========================================

@app.route('/')
@login_required
def index():
    palavras = Palavra.query.filter_by(user_id=current_user.id).order_by(Palavra.palavra).all()
    return render_template('index.html', palavras=[p.palavra for p in palavras])

@app.route('/traduzir', methods=['POST'])
@login_required
def traduzir():
    dados = request.get_json()
    return jsonify(traduzir_com_fallback(dados.get('palavra', '').strip(), dados.get('idioma', '').strip()))

@app.route('/adicionar', methods=['POST'])
@login_required
def adicionar():
    dados = request.get_json()
    palavra_texto = dados.get('palavra', '').strip()
    idioma = dados.get('idioma', '').strip()
    traducao_texto = dados.get('traducao', '').strip()
    
    if not all([palavra_texto, idioma, traducao_texto]):
        return jsonify({"erro": "Preencha todos os campos"}), 400
    
    palavra_obj = Palavra.query.filter_by(palavra=palavra_texto, user_id=current_user.id).first()
    if not palavra_obj:
        palavra_obj = Palavra(palavra=palavra_texto, user_id=current_user.id)
        db.session.add(palavra_obj)
        db.session.flush()
    
    trad_existente = Traducao.query.filter_by(palavra_id=palavra_obj.id, idioma=idioma).first()
    if trad_existente:
        trad_existente.traducao = traducao_texto
    else:
        db.session.add(Traducao(palavra_id=palavra_obj.id, idioma=idioma, traducao=traducao_texto))
    
    db.session.commit()
    return jsonify({"sucesso": f"'{palavra_texto}' adicionado!"})

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
    if len(query) < 2: return jsonify([])
    palavras = Palavra.query.filter(Palavra.user_id == current_user.id, Palavra.palavra.ilike(f'%{query}%')).limit(10).all()
    return jsonify([p.palavra for p in palavras])

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