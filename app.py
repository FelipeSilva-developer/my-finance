from __future__ import annotations
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
import os
import sys
import uuid
import webbrowser
from threading import Timer
from pathlib import Path
import pytz

from flask import Flask, flash, redirect, render_template, request, url_for, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import extract
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect

BASE_DIR_PATH = Path(__file__).resolve().parent
ZERO = Decimal("0.00")

def get_today_br():
    return datetime.now(pytz.timezone('America/Sao_Paulo')).date()

# --- CONFIGURAÇÃO DE PASTAS ---
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
    DATABASE_PATH = BASE_DIR / "financeiro.db"
    template_dir = os.path.join(sys._MEIPASS, 'templates')
    static_dir = os.path.join(sys._MEIPASS, 'static')
    
    env_path = os.path.join(sys._MEIPASS, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
else:
    BASE_DIR = BASE_DIR_PATH
    DATABASE_PATH = BASE_DIR / "financeiro.db"
    template_dir = os.path.join(BASE_DIR, 'templates')
    static_dir = os.path.join(BASE_DIR, 'static')
    load_dotenv()

# --- CRIAÇÃO DO APP ---
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---
database_url = os.environ.get("DATABASE_URL")

if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DATABASE_PATH.as_posix()}"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "financas-secret-key-local")

# Prevenção de erro 500 no Vercel
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

csrf = CSRFProtect(app)
db = SQLAlchemy(app)


# --- MODELOS DE BANCO DE DADOS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    movimentacoes = db.relationship('Movimentacao', backref='user', lazy=True, cascade="all, delete-orphan")
    contas = db.relationship('ContaPagar', backref='user', lazy=True, cascade="all, delete-orphan")
    metas = db.relationship('MetaPatrimonial', backref='user', lazy=True, cascade="all, delete-orphan")
    investimentos = db.relationship('Investimento', backref='user', lazy=True, cascade="all, delete-orphan")
    cartoes = db.relationship('CartaoCredito', backref='user', lazy=True, cascade="all, delete-orphan")
    despesas_cartao = db.relationship('DespesaCartao', backref='user', lazy=True, cascade="all, delete-orphan")
    orcamentos = db.relationship('OrcamentoMensal', backref='user', lazy=True, cascade="all, delete-orphan")

class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.String(20), nullable=False) 

class OrcamentoMensal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    limite = db.Column(db.Numeric(12, 2), nullable=False, default=ZERO)

class Movimentacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    descricao = db.Column(db.String(160), nullable=False)
    categoria = db.Column(db.String(50), nullable=False) 
    valor = db.Column(db.Numeric(12, 2), nullable=False, default=ZERO)
    data_registro = db.Column(db.Date, nullable=False, default=get_today_br)

class ContaPagar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    descricao = db.Column(db.String(160), nullable=False)
    categoria = db.Column(db.String(50), nullable=False) 
    valor = db.Column(db.Numeric(12, 2), nullable=False, default=ZERO)
    data_vencimento = db.Column(db.Date, nullable=False)
    pago = db.Column(db.Boolean, nullable=False, default=False)
    parcela_atual = db.Column(db.Integer, nullable=False, default=1)
    total_parcelas = db.Column(db.Integer, nullable=False, default=1)
    grupo_recorrencia_id = db.Column(db.String(50), nullable=True)
    @property
    def is_fatura(self): return False

class MetaPatrimonial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    objetivo = db.Column(db.String(100), nullable=False)
    valor_alvo = db.Column(db.Numeric(12, 2), nullable=False, default=ZERO)
    prazo_meses = db.Column(db.Integer, nullable=False, default=12)
    aportes = db.relationship('Investimento', backref='meta', lazy=True)

class Investimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ativo = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    taxa_rendimento = db.Column(db.String(100), nullable=True)
    valor_aporte = db.Column(db.Numeric(12, 2), nullable=False, default=ZERO)
    valor_atual = db.Column(db.Numeric(12, 2), nullable=False, default=ZERO)
    data_aporte = db.Column(db.Date, nullable=False, default=get_today_br)
    meta_id = db.Column(db.Integer, db.ForeignKey('meta_patrimonial.id'), nullable=True)
    resgatado = db.Column(db.Boolean, nullable=False, default=False)

class CartaoCredito(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    nome = db.Column(db.String(50), nullable=False)
    limite = db.Column(db.Numeric(12, 2), nullable=False, default=ZERO)
    dia_fechamento = db.Column(db.Integer, nullable=False, default=5)
    dia_vencimento = db.Column(db.Integer, nullable=False, default=10)
    despesas = db.relationship('DespesaCartao', backref='cartao', lazy=True, cascade="all, delete-orphan")

class DespesaCartao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    descricao = db.Column(db.String(160), nullable=False)
    valor = db.Column(db.Numeric(12, 2), nullable=False, default=ZERO)
    data_compra = db.Column(db.Date, nullable=False)
    mes_fatura = db.Column(db.Integer, nullable=False)
    ano_fatura = db.Column(db.Integer, nullable=False)
    parcela_atual = db.Column(db.Integer, nullable=False, default=1)
    total_parcelas = db.Column(db.Integer, nullable=False, default=1)
    categoria = db.Column(db.String(50), nullable=False, default="Outros")
    pago = db.Column(db.Boolean, nullable=False, default=False)
    cartao_id = db.Column(db.Integer, db.ForeignKey('cartao_credito.id'), nullable=False)
    grupo_id = db.Column(db.String(50), nullable=True)

class FaturaVirtual:
    def __init__(self, cartao_id, nome_cartao, mes, ano, dia_vencimento, despesas):
        self.id = f"fat_{cartao_id}_{mes}_{ano}"
        self.cartao_id = cartao_id
        self.descricao = f"Fatura {nome_cartao}"
        self.categoria = "Cartão de Crédito"
        self.valor = sum([to_decimal(d.valor) for d in despesas])
        self.pago = len(despesas) > 0 and all([d.pago for d in despesas])
        self.mes = mes
        self.ano = ano
        self.total_parcelas = 1
        self.parcela_atual = 1
        self.is_fatura = True
        try:
            self.data_vencimento = date(ano, mes, dia_vencimento)
        except ValueError:
            import calendar
            _, last_day = calendar.monthrange(ano, mes)
            self.data_vencimento = date(ano, mes, min(dia_vencimento, last_day))

# --- FUNÇÕES AUXILIARES ---
def to_decimal(value: object) -> Decimal:
    if value in (None, ""): return ZERO
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

@app.template_filter("brl")
def brl_filter(value) -> str:
    dec_val = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return "R$ " + f"{dec_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def adicionar_meses(orig_date: date, months: int) -> date:
    target_month = orig_date.month + months
    target_year = orig_date.year + (target_month - 1) // 12
    target_month = (target_month - 1) % 12 + 1
    target_day = min(orig_date.day, [31, 29 if target_year % 4 == 0 and (target_year % 100 != 0 or target_year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][target_month - 1])
    return date(target_year, target_month, target_day)

def calcular_fatura(data_compra: date, dia_fechamento: int, parcela_n: int) -> tuple[int, int]:
    dt = adicionar_meses(data_compra, parcela_n)
    if data_compra.day >= dia_fechamento:
        dt = adicionar_meses(dt, 1)
    return dt.month, dt.year

# --- DECORADORES ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if not session.get("is_admin"):
            flash("Acesso restrito a Administradores.", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated_function

def normal_user_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if session.get("is_admin"):
            return redirect(url_for("configuracoes"))
        return f(*args, **kwargs)
    return decorated_function

# --- ROTA PARA O SERVICE WORKER (PWA) ---
@app.route('/sw.js')
def sw():
    return app.send_static_file('sw.js')

# --- ROTAS DE AUTENTICAÇÃO ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username").strip()
        senha = request.form.get("senha")
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, senha):
            session["user_id"] = user.id
            session["username"] = user.username
            session["is_admin"] = user.is_admin
            if user.is_admin:
                return redirect(url_for("configuracoes"))
            return redirect(url_for("dashboard"))
        else:
            flash("Usuário ou palavra-passe incorretos.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- ROTAS DA APLICAÇÃO (USUÁRIOS COMUNS) ---

@app.route("/", methods=["GET"])
@normal_user_required
def dashboard():
    hoje = get_today_br()
    uid = session["user_id"]
    view_mode = request.args.get("view", "mensal")
    selected_month = int(request.args.get("month", hoje.month))
    selected_year = int(request.args.get("year", hoje.year))
    current_tab = request.args.get("tab", "tab-visao")

    categorias_despesa = Categoria.query.filter_by(tipo='despesa').order_by(Categoria.nome.asc()).all()
    cartoes = CartaoCredito.query.filter_by(user_id=uid).all()

    if view_mode == "mensal":
        mov_query = Movimentacao.query.filter(Movimentacao.user_id==uid, extract('month', Movimentacao.data_registro) == selected_month, extract('year', Movimentacao.data_registro) == selected_year)
        contas_query = ContaPagar.query.filter(ContaPagar.user_id==uid, extract('month', ContaPagar.data_vencimento) == selected_month, extract('year', ContaPagar.data_vencimento) == selected_year)
        inv_query = Investimento.query.filter(Investimento.user_id==uid, extract('month', Investimento.data_aporte) == selected_month, extract('year', Investimento.data_aporte) == selected_year)
        despesas_cartao = DespesaCartao.query.filter_by(user_id=uid, mes_fatura=selected_month, ano_fatura=selected_year).all()
    else:
        mov_query = Movimentacao.query.filter(Movimentacao.user_id==uid, extract('year', Movimentacao.data_registro) == selected_year)
        contas_query = ContaPagar.query.filter(ContaPagar.user_id==uid, extract('year', ContaPagar.data_vencimento) == selected_year)
        inv_query = Investimento.query.filter(Investimento.user_id==uid, extract('year', Investimento.data_aporte) == selected_year)
        despesas_cartao = DespesaCartao.query.filter_by(user_id=uid, ano_fatura=selected_year).all()

    movimentacoes = mov_query.order_by(Movimentacao.data_registro.desc()).all()
    contas = contas_query.order_by(ContaPagar.data_vencimento.asc()).all()
    investimentos_mes = inv_query.order_by(Investimento.data_aporte.desc()).all()
    carteira_ativa = Investimento.query.filter_by(user_id=uid, resgatado=False).order_by(Investimento.data_aporte.desc()).all()
    metas_db = MetaPatrimonial.query.filter_by(user_id=uid).all()

    faturas_virtuais = []
    for cartao in cartoes:
        if view_mode == "mensal":
            desp_cartao = [dc for dc in despesas_cartao if dc.cartao_id == cartao.id]
            if desp_cartao:
                faturas_virtuais.append(FaturaVirtual(cartao.id, cartao.nome, selected_month, selected_year, cartao.dia_vencimento, desp_cartao))
        else:
            desp_by_mes = {}
            for dc in despesas_cartao:
                if dc.cartao_id == cartao.id: desp_by_mes.setdefault(dc.mes_fatura, []).append(dc)
            for mes, desps in desp_by_mes.items():
                faturas_virtuais.append(FaturaVirtual(cartao.id, cartao.nome, mes, selected_year, cartao.dia_vencimento, desps))
    
    itens_cronograma = list(contas) + faturas_virtuais
    itens_cronograma.sort(key=lambda x: x.data_vencimento)

    metas_progresso = []
    for meta in metas_db:
        aportes_ativos_meta = [i for i in meta.aportes if not i.resgatado]
        total_acumulado = sum([to_decimal(i.valor_atual) for i in aportes_ativos_meta])
        pct = (total_acumulado / meta.valor_alvo * Decimal("100")) if meta.valor_alvo > ZERO else ZERO
        valor_restante = meta.valor_alvo - total_acumulado
        sugestao_mensal = (valor_restante / Decimal(meta.prazo_meses)) if (valor_restante > ZERO and meta.prazo_meses > 0) else ZERO
        metas_progresso.append({
            'id': meta.id, 'objetivo': meta.objetivo, 'valor_alvo': meta.valor_alvo,
            'total_acumulado': total_acumulado, 'pct': float(pct.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),
            'prazo_meses': meta.prazo_meses, 'sugestao_mensal': sugestao_mensal
        })

    total_receitas = sum([to_decimal(m.valor) for m in movimentacoes])
    total_investido_mes = sum([to_decimal(i.valor_aporte) for i in investimentos_mes])
    total_contas_pendentes = sum([to_decimal(c.valor) for c in contas if not c.pago]) + sum([to_decimal(dc.valor) for dc in despesas_cartao if not dc.pago])
    total_contas_pagas = sum([to_decimal(c.valor) for c in contas if c.pago]) + sum([to_decimal(dc.valor) for dc in despesas_cartao if dc.pago])

    saldo_consolidado = total_receitas - total_contas_pagas - total_investido_mes
    patrimonio_total_acumulado = sum([to_decimal(i.valor_atual) for i in carteira_ativa])

    gastos_por_categoria = {}
    for c in contas: gastos_por_categoria[c.categoria] = gastos_por_categoria.get(c.categoria, ZERO) + to_decimal(c.valor)
    for dc in despesas_cartao: gastos_por_categoria[dc.categoria] = gastos_por_categoria.get(dc.categoria, ZERO) + to_decimal(dc.valor)
    
    chart_labels = list(gastos_por_categoria.keys())
    chart_data = [float(val) for val in gastos_por_categoria.values()]

    orcamentos_db = OrcamentoMensal.query.filter_by(user_id=uid).all()
    orcamentos_progresso = []
    for orc in orcamentos_db:
        gasto_cat = gastos_por_categoria.get(orc.categoria, ZERO)
        pct = (gasto_cat / orc.limite * 100) if orc.limite > 0 else 0
        orcamentos_progresso.append({
            'id': orc.id, 'categoria': orc.categoria, 'limite': orc.limite, 
            'gasto': gasto_cat, 'pct': float(pct.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        })

    anual_receitas = [0.0] * 12
    anual_despesas = [0.0] * 12
    if view_mode == "anual":
        for m in range(1, 13):
            m_mov = Movimentacao.query.filter(Movimentacao.user_id==uid, extract('month', Movimentacao.data_registro) == m, extract('year', Movimentacao.data_registro) == selected_year).all()
            m_ct = ContaPagar.query.filter(ContaPagar.user_id==uid, extract('month', ContaPagar.data_vencimento) == m, extract('year', ContaPagar.data_vencimento) == selected_year).all()
            m_dc = DespesaCartao.query.filter_by(user_id=uid, mes_fatura=m, ano_fatura=selected_year).all()
            anual_receitas[m-1] = float(sum([to_decimal(x.valor) for x in m_mov]))
            anual_despesas[m-1] = float(sum([to_decimal(x.valor) for x in m_ct]) + sum([to_decimal(x.valor) for x in m_dc]))

    meses_nomes = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 
                   7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}

    return render_template(
        "dashboard.html",
        movimentacoes=movimentacoes, itens_cronograma=itens_cronograma, carteira_ativa=carteira_ativa,
        metas_progresso=metas_progresso, orcamentos_progresso=orcamentos_progresso, total_receitas=total_receitas, total_investido=total_investido_mes,
        total_contas_pendentes=total_contas_pendentes, total_contas_pagas=total_contas_pagas,
        saldo_consolidado=saldo_consolidado, patrimonio_total_acumulado=patrimonio_total_acumulado,
        chart_labels=chart_labels, chart_data=chart_data, view_mode=view_mode,
        selected_month=selected_month, selected_year=selected_year, meses_nomes=meses_nomes, hoje=hoje,
        categorias_despesa=categorias_despesa, cartoes=cartoes, despesas_cartao=despesas_cartao, 
        current_tab=current_tab, anual_receitas=anual_receitas, anual_despesas=anual_despesas, metas=metas_db
    )

@app.route("/meus_cartoes", methods=["GET"])
@normal_user_required
def meus_cartoes():
    cartoes = CartaoCredito.query.filter_by(user_id=session["user_id"]).all()
    return render_template("meus_cartoes.html", cartoes=cartoes)

# --- ROTA DE AJUDA ---
@app.route("/ajuda", methods=["GET"])
@normal_user_required
def ajuda():
    return render_template("ajuda.html")

# --- NOVA ROTA DE EXPORTAÇÃO PDF ---
@app.route("/relatorio_pdf/<int:mes>/<int:ano>")
@normal_user_required
def relatorio_pdf(mes, ano):
    uid = session["user_id"]
    mov_query = Movimentacao.query.filter(Movimentacao.user_id==uid, extract('month', Movimentacao.data_registro) == mes, extract('year', Movimentacao.data_registro) == ano).order_by(Movimentacao.data_registro.desc()).all()
    contas_query = ContaPagar.query.filter(ContaPagar.user_id==uid, extract('month', ContaPagar.data_vencimento) == mes, extract('year', ContaPagar.data_vencimento) == ano).order_by(ContaPagar.data_vencimento.asc()).all()
    
    total_receitas = sum([to_decimal(m.valor) for m in mov_query])
    total_despesas = sum([to_decimal(c.valor) for c in contas_query])
    saldo = total_receitas - total_despesas
    
    return render_template("relatorio.html", receitas=mov_query, despesas=contas_query, mes=mes, ano=ano, total_receitas=total_receitas, total_despesas=total_despesas, saldo=saldo)


# --- ROTAS DO ADMIN ---
@app.route("/configuracoes", methods=["GET"])
@admin_required
def configuracoes():
    categorias_despesa = Categoria.query.filter_by(tipo='despesa').order_by(Categoria.nome.asc()).all()
    usuarios = User.query.all()
    return render_template("config.html", categorias_despesa=categorias_despesa, usuarios=usuarios)

@app.route("/admin/user/add", methods=["POST"])
@admin_required
def add_user():
    username = request.form.get("username").strip()
    senha = request.form.get("senha")
    is_admin = request.form.get("is_admin") == "sim"
    if username and senha:
        if not User.query.filter_by(username=username).first():
            db.session.add(User(username=username, password_hash=generate_password_hash(senha), is_admin=is_admin))
            db.session.commit()
            flash("Usuário criado com sucesso!", "success")
        else:
            flash("Este nome de usuário já existe.", "error")
    return redirect(url_for("configuracoes"))

@app.route("/admin/user/<int:id>/edit", methods=["POST"])
@admin_required
def edit_user(id):
    user = User.query.get_or_404(id)
    senha = request.form.get("senha")
    if senha:
        user.password_hash = generate_password_hash(senha)
        db.session.commit()
        flash(f"Senha do usuário {user.username} atualizada!", "success")
    return redirect(url_for("configuracoes"))

@app.route("/admin/user/<int:id>/delete", methods=["POST"])
@admin_required
def delete_user(id):
    if id == session["user_id"]:
        flash("Operação negada. Você não pode excluir a sua própria conta logada.", "error")
        return redirect(url_for("configuracoes"))
    
    user = User.query.get_or_404(id)
    db.session.delete(user)
    db.session.commit()
    flash(f"Usuário '{user.username}' e todos os seus dados foram excluídos do sistema.", "success")
    return redirect(url_for("configuracoes"))

@app.route("/categoria/add", methods=["POST"])
@admin_required
def add_categoria():
    nome = request.form.get("nome", "").strip()
    if nome and not Categoria.query.filter_by(nome=nome, tipo='despesa').first():
        db.session.add(Categoria(nome=nome, tipo='despesa'))
        db.session.commit()
    return redirect(url_for("configuracoes"))

@app.route("/categoria/<int:id>/delete", methods=["POST"])
@admin_required
def delete_categoria(id):
    cat = Categoria.query.get_or_404(id)
    db.session.delete(cat)
    db.session.commit()
    return redirect(url_for("configuracoes"))

# --- ROTAS DE ORÇAMENTO MENSAL ---
@app.route("/orcamento/add", methods=["POST"])
@normal_user_required
def add_orcamento():
    categoria = request.form.get("categoria")
    limite = to_decimal(request.form.get("limite"))
    if categoria and limite > ZERO:
        orc_existente = OrcamentoMensal.query.filter_by(user_id=session["user_id"], categoria=categoria).first()
        if orc_existente: orc_existente.limite = limite
        else: db.session.add(OrcamentoMensal(user_id=session["user_id"], categoria=categoria, limite=limite))
        db.session.commit()
    return redirect(url_for("dashboard", tab="tab-visao"))

@app.route("/orcamento/<int:id>/delete", methods=["POST"])
@normal_user_required
def delete_orcamento(id):
    orc = OrcamentoMensal.query.filter_by(id=id, user_id=session["user_id"]).first_or_404()
    db.session.delete(orc)
    db.session.commit()
    return redirect(url_for("dashboard", tab="tab-visao"))

# --- ROTAS DE FLUXO DE CAIXA (USUÁRIOS COMUNS) ---
@app.route("/receita/add", methods=["POST"])
@normal_user_required
def add_receita():
    descricao = request.form.get("descricao", "").strip()
    categoria = request.form.get("categoria", "Salário")
    valor = to_decimal(request.form.get("valor"))
    data_str = request.form.get("data")
    data_mov = datetime.strptime(data_str, "%Y-%m-%d").date() if data_str else get_today_br()

    db.session.add(Movimentacao(user_id=session["user_id"], descricao=descricao, categoria=categoria, valor=valor, data_registro=data_mov))
    db.session.commit()
    return redirect(url_for("dashboard", month=data_mov.month, year=data_mov.year, tab="tab-visao"))

@app.route("/receita/<int:id>/edit", methods=["POST"])
@normal_user_required
def edit_receita(id):
    m = Movimentacao.query.filter_by(id=id, user_id=session["user_id"]).first_or_404()
    m.descricao = request.form.get("descricao", "").strip()
    m.categoria = request.form.get("categoria")
    m.valor = to_decimal(request.form.get("valor"))
    data_str = request.form.get("data")
    if data_str: m.data_registro = datetime.strptime(data_str, "%Y-%m-%d").date()
    db.session.commit()
    return redirect(url_for("dashboard", month=m.data_registro.month, year=m.data_registro.year, tab="tab-visao"))

@app.route("/receita/<int:id>/delete", methods=["POST"])
@normal_user_required
def delete_receita(id):
    m = Movimentacao.query.filter_by(id=id, user_id=session["user_id"]).first_or_404()
    month, year = m.data_registro.month, m.data_registro.year
    db.session.delete(m)
    db.session.commit()
    return redirect(url_for("dashboard", month=month, year=year, tab="tab-visao"))

@app.route("/conta/add", methods=["POST"])
@normal_user_required
def add_conta():
    descricao = request.form.get("descricao", "").strip()
    categoria = request.form.get("categoria", "Outros")
    valor_total = to_decimal(request.form.get("valor"))
    vencimento_str = request.form.get("data_vencimento")
    tipo_lancamento = request.form.get("tipo_lancamento", "unico")
    total_parcelas = int(request.form.get("total_parcelas", 1))
    parcela_inicial = int(request.form.get("parcela_inicial", 1))

    if not descricao or valor_total <= ZERO or not vencimento_str: return redirect(url_for("dashboard", tab="tab-visao"))
    data_venc_inicial = datetime.strptime(vencimento_str, "%Y-%m-%d").date()

    if tipo_lancamento == "parcelado" and total_parcelas > 1:
        if parcela_inicial > total_parcelas: parcela_inicial = total_parcelas
        grupo_id = str(uuid.uuid4())[:8]
        valor_parcela = (valor_total / total_parcelas).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        for i, num_parcela in enumerate(range(parcela_inicial, total_parcelas + 1)):
            data_venc = adicionar_meses(data_venc_inicial, i)
            nova_conta = ContaPagar(
                user_id=session["user_id"], descricao=f"{descricao} ({num_parcela}/{total_parcelas})",
                categoria=categoria, valor=valor_parcela, data_vencimento=data_venc,
                pago=False, parcela_atual=num_parcela, total_parcelas=total_parcelas, grupo_recorrencia_id=grupo_id
            )
            db.session.add(nova_conta)
            
    elif tipo_lancamento == "assinatura":
        # Gera parcelas contínuas para os próximos 5 anos (60 meses)
        grupo_id = "ass_" + str(uuid.uuid4())[:8]
        for i in range(60):
            data_venc = adicionar_meses(data_venc_inicial, i)
            nova_conta = ContaPagar(
                user_id=session["user_id"], descricao=f"{descricao} (Assinatura)",
                categoria=categoria, valor=valor_total, data_vencimento=data_venc,
                pago=False, parcela_atual=i+1, total_parcelas=999, grupo_recorrencia_id=grupo_id
            )
            db.session.add(nova_conta)
            
    else:
        db.session.add(ContaPagar(user_id=session["user_id"], descricao=descricao, categoria=categoria, valor=valor_total, data_vencimento=data_venc_inicial, pago=False))

    db.session.commit()
    return redirect(url_for("dashboard", month=data_venc_inicial.month, year=data_venc_inicial.year, tab="tab-cronograma"))

@app.route("/conta/<int:id>/edit", methods=["POST"])
@normal_user_required
def edit_conta(id):
    c = ContaPagar.query.filter_by(id=id, user_id=session["user_id"]).first_or_404()
    c.descricao = request.form.get("descricao", "").strip()
    c.categoria = request.form.get("categoria")
    c.valor = to_decimal(request.form.get("valor"))
    venc_str = request.form.get("data_vencimento")
    if venc_str: c.data_vencimento = datetime.strptime(venc_str, "%Y-%m-%d").date()
    db.session.commit()
    return redirect(url_for("dashboard", month=c.data_vencimento.month, year=c.data_vencimento.year, tab="tab-cronograma"))

@app.route("/conta/<int:conta_id>/toggle", methods=["POST"])
@normal_user_required
def toggle_conta(conta_id):
    conta = ContaPagar.query.filter_by(id=conta_id, user_id=session["user_id"]).first_or_404()
    conta.pago = not conta.pago
    db.session.commit()
    return redirect(url_for("dashboard", month=conta.data_vencimento.month, year=conta.data_vencimento.year, tab='tab-cronograma'))

@app.route("/conta/<int:conta_id>/delete", methods=["POST"])
@normal_user_required
def delete_conta(conta_id):
    conta = ContaPagar.query.filter_by(id=conta_id, user_id=session["user_id"]).first_or_404()
    m, y = conta.data_vencimento.month, conta.data_vencimento.year
    if request.form.get("deletar_tudo") == "sim" and conta.grupo_recorrencia_id:
        ContaPagar.query.filter_by(user_id=session["user_id"], grupo_recorrencia_id=conta.grupo_recorrencia_id, pago=False).delete()
    else: db.session.delete(conta)
    db.session.commit()
    return redirect(url_for("dashboard", month=m, year=y, tab='tab-cronograma'))

# --- ROTAS DE GESTÃO DE CARTÕES E DESPESAS (USUÁRIOS COMUNS) ---
@app.route("/cartao/add", methods=["POST"])
@normal_user_required
def add_cartao():
    nome = request.form.get("nome", "").strip()
    limite = to_decimal(request.form.get("limite"))
    dia_f = int(request.form.get("dia_fechamento", 5))
    dia_v = int(request.form.get("dia_vencimento", 10))
    if nome and limite > ZERO:
        db.session.add(CartaoCredito(user_id=session["user_id"], nome=nome, limite=limite, dia_fechamento=dia_f, dia_vencimento=dia_v))
        db.session.commit()
    return redirect(url_for("meus_cartoes"))

@app.route("/cartao/<int:id>/edit", methods=["POST"])
@normal_user_required
def edit_cartao(id):
    cartao = CartaoCredito.query.filter_by(id=id, user_id=session["user_id"]).first_or_404()
    cartao.nome = request.form.get("nome", "").strip()
    cartao.limite = to_decimal(request.form.get("limite"))
    cartao.dia_fechamento = int(request.form.get("dia_fechamento", 5))
    cartao.dia_vencimento = int(request.form.get("dia_vencimento", 10))
    db.session.commit()
    return redirect(url_for("meus_cartoes"))

@app.route("/cartao/<int:id>/delete", methods=["POST"])
@normal_user_required
def delete_cartao(id):
    cartao = CartaoCredito.query.filter_by(id=id, user_id=session["user_id"]).first_or_404()
    db.session.delete(cartao)
    db.session.commit()
    return redirect(url_for("meus_cartoes"))

@app.route("/cartao/despesa/add", methods=["POST"])
@normal_user_required
def add_despesa_cartao():
    cartao_id = int(request.form.get("cartao_id", 0))
    descricao = request.form.get("descricao", "").strip()
    valor_total = to_decimal(request.form.get("valor"))
    data_str = request.form.get("data_compra")
    categoria = request.form.get("categoria", "Outros")
    total_parcelas = int(request.form.get("total_parcelas", 1))

    cartao = CartaoCredito.query.filter_by(id=cartao_id, user_id=session["user_id"]).first_or_404()
    data_compra = datetime.strptime(data_str, "%Y-%m-%d").date() if data_str else get_today_br()
    grupo_id = str(uuid.uuid4())[:8] if total_parcelas > 1 else None
    valor_parcela = (valor_total / total_parcelas).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    for i in range(total_parcelas):
        m_fat, y_fat = calcular_fatura(data_compra, cartao.dia_fechamento, i)
        desc = f"{descricao} ({i+1}/{total_parcelas})" if total_parcelas > 1 else descricao
        db.session.add(DespesaCartao(
            user_id=session["user_id"], descricao=desc, valor=valor_parcela, data_compra=data_compra,
            mes_fatura=m_fat, ano_fatura=y_fat, parcela_atual=i+1, total_parcelas=total_parcelas,
            categoria=categoria, pago=False, cartao_id=cartao_id, grupo_id=grupo_id
        ))
    db.session.commit()
    return redirect(url_for("dashboard", month=data_compra.month, year=data_compra.year, tab="tab-cartao"))

@app.route("/cartao/despesa/<int:id>/edit", methods=["POST"])
@normal_user_required
def edit_despesa_cartao(id):
    dc = DespesaCartao.query.filter_by(id=id, user_id=session["user_id"]).first_or_404()
    dc.descricao = request.form.get("descricao", "").strip()
    dc.valor = to_decimal(request.form.get("valor"))
    dc.categoria = request.form.get("categoria")
    db.session.commit()
    return redirect(url_for("dashboard", month=dc.mes_fatura, year=dc.ano_fatura, tab="tab-cartao"))

@app.route("/cartao/despesa/<int:id>/toggle", methods=["POST"])
@normal_user_required
def toggle_despesa_cartao(id):
    dc = DespesaCartao.query.filter_by(id=id, user_id=session["user_id"]).first_or_404()
    dc.pago = not dc.pago
    db.session.commit()
    return redirect(url_for("dashboard", month=dc.mes_fatura, year=dc.ano_fatura, tab="tab-cartao"))

@app.route("/cartao/despesa/<int:id>/delete", methods=["POST"])
@normal_user_required
def delete_despesa_cartao(id):
    dc = DespesaCartao.query.filter_by(id=id, user_id=session["user_id"]).first_or_404()
    m, y = dc.mes_fatura, dc.ano_fatura
    if request.form.get("deletar_tudo") == "sim" and dc.grupo_id:
        DespesaCartao.query.filter_by(user_id=session["user_id"], grupo_id=dc.grupo_id).delete()
    else: db.session.delete(dc)
    db.session.commit()
    return redirect(url_for("dashboard", month=m, year=y, tab="tab-cartao"))

@app.route("/fatura/<int:cartao_id>/<int:mes>/<int:ano>/toggle", methods=["POST"])
@normal_user_required
def toggle_fatura(cartao_id, mes, ano):
    despesas = DespesaCartao.query.filter_by(user_id=session["user_id"], cartao_id=cartao_id, mes_fatura=mes, ano_fatura=ano).all()
    if despesas:
        all_paid = all(d.pago for d in despesas)
        for d in despesas: d.pago = not all_paid
        db.session.commit()
    return redirect(url_for("dashboard", month=mes, year=ano, tab="tab-cronograma"))

# --- ROTAS DE INVESTIMENTOS E METAS (USUÁRIOS COMUNS) ---
@app.route("/investimento/add", methods=["POST"])
@normal_user_required
def add_investimento():
    ativo = request.form.get("ativo", "").strip().upper()
    tipo = request.form.get("tipo", "Renda Fixa")
    taxa = request.form.get("taxa_rendimento", "").strip()
    valor = to_decimal(request.form.get("valor_aporte"))
    data_str = request.form.get("data_aporte")
    meta_id = request.form.get("meta_id")
    data_ap = datetime.strptime(data_str, "%Y-%m-%d").date() if data_str else get_today_br()

    db.session.add(Investimento(
        user_id=session["user_id"], ativo=ativo, tipo=tipo, taxa_rendimento=taxa, valor_aporte=valor, 
        valor_atual=valor, data_aporte=data_ap, meta_id=int(meta_id) if meta_id else None
    ))
    db.session.commit()
    return redirect(url_for("dashboard", month=data_ap.month, year=data_ap.year, tab="tab-patrimonio"))

@app.route("/investimento/<int:id>/edit", methods=["POST"])
@normal_user_required
def edit_investimento(id):
    i = Investimento.query.filter_by(id=id, user_id=session["user_id"]).first_or_404()
    i.ativo = request.form.get("ativo", "").strip().upper()
    i.tipo = request.form.get("tipo")
    i.taxa_rendimento = request.form.get("taxa_rendimento", "").strip()
    i.valor_aporte = to_decimal(request.form.get("valor_aporte"))
    i.valor_atual = to_decimal(request.form.get("valor_atual"))
    data_str = request.form.get("data_aporte")
    if data_str: i.data_aporte = datetime.strptime(data_str, "%Y-%m-%d").date()
    db.session.commit()
    return redirect(url_for("dashboard", tab="tab-patrimonio"))

@app.route("/investimento/<int:id>/update", methods=["POST"])
@normal_user_required
def update_investimento(id):
    inv = Investimento.query.filter_by(id=id, user_id=session["user_id"]).first_or_404()
    novo_valor = to_decimal(request.form.get("valor_atual"))
    if novo_valor >= ZERO:
        inv.valor_atual = novo_valor
        db.session.commit()
    return redirect(url_for("dashboard", tab="tab-patrimonio"))

@app.route("/investimento/<int:id>/resgatar", methods=["POST"])
@normal_user_required
def resgatar_investimento(id):
    inv = Investimento.query.filter_by(id=id, user_id=session["user_id"]).first_or_404()
    db.session.add(Movimentacao(
        user_id=session["user_id"], descricao=f"Resgate: {inv.ativo} ({inv.taxa_rendimento})",
        categoria="Renda Extra", valor=inv.valor_atual, data_registro=get_today_br()
    ))
    inv.resgatado = True
    inv.meta_id = None 
    db.session.commit()
    return redirect(url_for("dashboard", tab="tab-patrimonio"))

@app.route("/investimento/<int:id>/delete", methods=["POST"])
@normal_user_required
def delete_investimento(id):
    inv = Investimento.query.filter_by(id=id, user_id=session["user_id"]).first_or_404()
    db.session.delete(inv)
    db.session.commit()
    return redirect(url_for("dashboard", tab="tab-patrimonio"))

@app.route("/meta/add", methods=["POST"])
@normal_user_required
def add_meta():
    obj = request.form.get("objetivo", "").strip()
    alvo = to_decimal(request.form.get("valor_alvo"))
    prazo = int(request.form.get("prazo_meses", 12))
    if obj and alvo > ZERO and prazo > 0:
        db.session.add(MetaPatrimonial(user_id=session["user_id"], objetivo=obj, valor_alvo=alvo, prazo_meses=prazo))
        db.session.commit()
    return redirect(url_for("dashboard", tab="tab-patrimonio"))

@app.route("/meta/<int:id>/edit", methods=["POST"])
@normal_user_required
def edit_meta(id):
    m = MetaPatrimonial.query.filter_by(id=id, user_id=session["user_id"]).first_or_404()
    m.objetivo = request.form.get("objetivo", "").strip()
    m.valor_alvo = to_decimal(request.form.get("valor_alvo"))
    m.prazo_meses = int(request.form.get("prazo_meses", 12))
    db.session.commit()
    return redirect(url_for("dashboard", tab="tab-patrimonio"))

@app.route("/meta/<int:id>/delete", methods=["POST"])
@normal_user_required
def delete_meta(id):
    meta = MetaPatrimonial.query.filter_by(id=id, user_id=session["user_id"]).first_or_404()
    for inv in meta.aportes: inv.meta_id = None
    db.session.delete(meta)
    db.session.commit()
    return redirect(url_for("dashboard", tab="tab-patrimonio"))

def open_browser():
    webbrowser.open("http://127.0.0.1:5005")

# Cria as tabelas e o Admin inicial através de Variáveis de Ambiente
with app.app_context():
    db.create_all()
    
    if User.query.count() == 0:
        admin_user = os.environ.get("ADMIN_USERNAME", "admin")
        admin_pass = os.environ.get("ADMIN_PASSWORD", "senha_segura_123")
        
        admin = User(username=admin_user, password_hash=generate_password_hash(admin_pass), is_admin=True)
        db.session.add(admin)
        db.session.commit()
        
    if Categoria.query.count() == 0:
        defaults = [('Moradia', 'despesa'), ('Transporte', 'despesa'), ('Lazer', 'despesa'), ('Outros', 'despesa')]
        for n, t in defaults: db.session.add(Categoria(nome=n, tipo=t))
        db.session.commit()

if __name__ == "__main__":
    Timer(1.5, open_browser).start()
    app.run(host="0.0.0.0", port=5005, debug=False)
