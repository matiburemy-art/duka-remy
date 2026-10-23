from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func
import os

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'duka-pro-2026-secret')

# Sur Render on écrit dans /tmp sinon read-only
if os.environ.get('RENDER'):
    db_path = '/tmp/duka.db'
else:
    db_path = os.path.join(basedir, 'duka.db')

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# MODELS
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(20), default='patron')

class Produit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    code_barre = db.Column(db.String(100), nullable=True)
    prix_achat = db.Column(db.Integer, nullable=False)
    prix_vente = db.Column(db.Integer, nullable=False)
    stock = db.Column(db.Integer, default=0)
    stock_min = db.Column(db.Integer, default=5)

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    telephone = db.Column(db.String(20))
    dette_totale = db.Column(db.Integer, default=0)

class Vente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.now)
    total = db.Column(db.Integer)
    benefice = db.Column(db.Integer)
    type_paiement = db.Column(db.String(20))

class VenteItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vente_id = db.Column(db.Integer, db.ForeignKey('vente.id'))
    produit_id = db.Column(db.Integer, db.ForeignKey('produit.id'))
    quantite = db.Column(db.Integer)
    prix = db.Column(db.Integer)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = User.query.filter_by(username=request.form['username']).first()
        if u and u.password == request.form['password']:
            login_user(u)
            return redirect(url_for('dashboard'))
        flash("Username ou password incorrect", "danger")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    produits = Produit.query.all()
    clients = Client.query.filter(Client.dette_totale > 0).all()
    today = datetime.now().date()
    ca_jour = db.session.query(func.sum(Vente.total)).filter(func.date(Vente.date)==today).scalar() or 0
    return render_template('dashboard.html', produits=produits, clients=clients, ca_jour=ca_jour)

# STOCK
@app.route('/stock', methods=['GET', 'POST'])
@login_required
def stock():
    if request.method == 'POST':
        code = request.form.get('code','').strip() or None
        p = Produit(
            nom=request.form.get('nom'),
            code_barre=code,
            prix_achat=int(request.form.get('achat') or 0),
            prix_vente=int(request.form.get('vente') or 0),
            stock=int(request.form.get('stock') or 0),
            stock_min=int(request.form.get('min') or 5)
        )
        db.session.add(p)
        db.session.commit()
        flash(f"{p.nom} ajouté !", "success")
        return redirect(url_for('stock'))
    produits = Produit.query.all()
    return render_template('stock.html', produits=produits)

@app.route('/stock/delete/<int:id>')
@login_required
def delete_produit(id):
    if current_user.role != 'patron':
        flash("Seul patron peut supprimer", "danger")
        return redirect(url_for('stock'))
    Produit.query.filter_by(id=id).delete()
    db.session.commit()
    flash("Produit supprimé", "success")
    return redirect(url_for('stock'))

@app.route('/stock/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_produit(id):
    p = Produit.query.get_or_404(id)
    if request.method == 'POST':
        p.nom = request.form.get('nom')
        p.code_barre = request.form.get('code') or None
        p.prix_achat = int(request.form.get('achat') or p.prix_achat)
        p.prix_vente = int(request.form.get('vente') or p.prix_vente)
        p.stock = int(request.form.get('stock') or p.stock)
        p.stock_min = int(request.form.get('min') or p.stock_min)
        db.session.commit()
        flash(f"{p.nom} modifié !", "success")
        return redirect(url_for('stock'))
    return render_template('edit_produit.html', p=p)

@app.route('/stock/achat/<int:id>', methods=['GET', 'POST'])
@login_required
def achat_stock(id):
    p = Produit.query.get_or_404(id)
    if request.method == 'POST':
        qte = int(request.form.get('qte') or 0)
        p.stock += qte
        if request.form.get('achat'):
            p.prix_achat = int(request.form.get('achat'))
        if request.form.get('vente'):
            p.prix_vente = int(request.form.get('vente'))
        db.session.commit()
        flash(f"Achat +{qte} | Stock {p.stock}", "success")
        return redirect(url_for('stock'))
    return render_template('achat_stock.html', p=p)

# CLIENTS
@app.route('/clients', methods=['GET', 'POST'])
@login_required
def clients():
    if request.method == 'POST':
        nom = request.form.get('nom','').strip()
        tel = request.form.get('telephone','').strip()
        dette_raw = request.form.get('dette','0').strip()
        if not nom:
            flash("Nom obligatoire", "danger")
            return redirect(url_for('clients'))
        try:
            dette = int(dette_raw) if dette_raw else 0
        except:
            dette = 0
        c = Client(nom=nom, telephone=tel, dette_totale=dette)
        db.session.add(c)
        db.session.commit()
        flash(f"Client {nom} ajouté !", "success")
        return redirect(url_for('clients'))
    all_clients = Client.query.all()
    return render_template('clients.html', clients=all_clients)

@app.route('/clients/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_client(id):
    c = Client.query.get_or_404(id)
    if request.method == 'POST':
        c.nom = request.form.get('nom')
        c.telephone = request.form.get('telephone')
        try:
            c.dette_totale = int(request.form.get('dette', 0))
        except:
            c.dette_totale = 0
        db.session.commit()
        flash(f"{c.nom} modifié", "success")
        return redirect(url_for('clients'))
    return render_template('edit_client.html', c=c)

@app.route('/clients/delete/<int:id>')
@login_required
def delete_client(id):
    c = Client.query.get_or_404(id)
    db.session.delete(c)
    db.session.commit()
    flash(f"Client {c.nom} supprimé", "success")
    return redirect(url_for('clients'))

@app.route('/clients/payer/<int:id>', methods=['POST'])
@login_required
def payer_dette(id):
    c = Client.query.get_or_404(id)
    montant = int(request.form.get('montant', 0))
    c.dette_totale = max(0, c.dette_totale - montant)
    db.session.commit()
    flash(f"Paiement {montant} FBU reçu", "success")
    return redirect(url_for('clients'))

# VENTE API
@app.route('/vente')
@login_required
def vente():
    produits = Produit.query.all()
    return render_template('vente.html', produits=produits)

@app.route('/api/produits')
@login_required
def api_produits():
    produits = Produit.query.all()
    return jsonify([{"id": p.id, "nom": p.nom, "code": p.code_barre, "prix": p.prix_vente, "stock": p.stock} for p in produits])

@app.route('/api/clients_simple')
@login_required
def api_clients_simple():
    return jsonify([{"id": c.id, "nom": c.nom, "dette": c.dette_totale} for c in Client.query.all()])

@app.route('/api/vente', methods=['POST'])
@login_required
def api_vente():
    data = request.json
    panier = data.get('panier', [])
    type_paiement = data.get('paiement', 'cash')
    client_id = data.get('client_id')
    total = 0
    benefice = 0
    for item in panier:
        p = Produit.query.get(item['id'])
        if not p or p.stock < item['qte']:
            return jsonify({"error": f"Stock insuffisant {p.nom if p else ''}"}), 400
        total += p.prix_vente * item['qte']
        benefice += (p.prix_vente - p.prix_achat) * item['qte']
    v = Vente(total=total, benefice=benefice, type_paiement=type_paiement)
    db.session.add(v)
    db.session.commit()
    for item in panier:
        p = Produit.query.get(item['id'])
        p.stock -= item['qte']
        db.session.add(VenteItem(vente_id=v.id, produit_id=p.id, quantite=item['qte'], prix=p.prix_vente))
    if type_paiement == 'dette' and client_id:
        c = Client.query.get(client_id)
        if c:
            c.dette_totale += total
    db.session.commit()
    return jsonify({"success": True})

# RAPPORT
@app.route('/rapport')
@login_required
def rapport():
    today = datetime.now().date()
    debut_semaine = today - timedelta(days=today.weekday())
    debut_mois = today.replace(day=1)
    debut_annee = today.replace(month=1, day=1)
    def stats(debut):
        debut_dt = datetime.combine(debut, datetime.min.time())
        ventes = Vente.query.filter(Vente.date >= debut_dt).all()
        return {"nb": len(ventes), "ca": sum([v.total for v in ventes]) if ventes else 0, "benef": sum([v.benefice for v in ventes]) if ventes else 0}
    data = {"jour": stats(today), "semaine": stats(debut_semaine), "mois": stats(debut_mois), "annee": stats(debut_annee)}
    faibles = Produit.query.filter(Produit.stock <= Produit.stock_min).all()
    dettes = Client.query.filter(Client.dette_totale > 0).order_by(Client.dette_totale.desc()).all()
    ventes_jour = Vente.query.filter(func.date(Vente.date) == today).order_by(Vente.date.desc()).all()
    return render_template('rapport.html', data=data, faibles=faibles, dettes=dettes, ventes=ventes_jour)

# USERS
@app.route('/users', methods=['GET', 'POST'])
@login_required
def users():
    if current_user.role != 'patron':
        flash("Accès patron seulement", "danger")
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','').strip()
        role = request.form.get('role','vendeur')
        if not username or not password:
            flash("Username et password obligatoires", "danger")
            return redirect(url_for('users'))
        if User.query.filter_by(username=username).first():
            flash("Username déjà pris", "danger")
            return redirect(url_for('users'))
        u = User(username=username, password=password, role=role)
        db.session.add(u)
        db.session.commit()
        flash(f"User {username} ajouté", "success")
        return redirect(url_for('users'))
    all_users = User.query.all()
    return render_template('users.html', users=all_users)

@app.route('/users/delete/<int:id>')
@login_required
def delete_user(id):
    if current_user.role != 'patron':
        flash("Patron seulement", "danger")
        return redirect(url_for('dashboard'))
    if id == current_user.id:
        flash("Tu ne peux pas te supprimer toi-même", "danger")
        return redirect(url_for('users'))
    User.query.filter_by(id=id).delete()
    db.session.commit()
    flash("User supprimé", "success")
    return redirect(url_for('users'))    

# CREATION DB - UNE SEULE FOIS A LA FIN
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='remy').first():
        db.session.add(User(username='remy', password='2005', role='patron'))
        db.session.commit()
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin', password='admin123', role='patron'))
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
