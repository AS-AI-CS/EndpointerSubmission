import flask #Import Dependencies
from flask_sqlalchemy import (SQLAlchemy) #Import SQL Alchemy for database
from flask_jwt_extended import (JWTManager, jwt_required, create_access_token, get_jwt_identity)#JWT Authentication Dependencies
from flasgger import Swagger #Swagger for API Docs as required by Endpointer YSWS
from flask_bcrypt import Bcrypt# Password Hashing for extra security
import datetime#To log time of entries
from sqlalchemy import desc#For ordering database queries
import requests#To make external API calls for prediction
from email_validator import validate_email, EmailNotValidError#For email validation function (check_email)

#Setup code
app = flask.Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///healthdb.db'#Database URI for SQLite
app.config['JWT_SECRET_KEY'] = 'ewrewghjkajk!34!'#Secret key for JWT

#Initialize extensions
db = SQLAlchemy(app)
jwt = JWTManager(app)
swagger = Swagger(app, template_file='docs.yml')#Link YAML file for Swagger docs
bcrypt = Bcrypt(app)

def check_email(email):#Email validation function for registration, basic, only checks if the email is in the right format (no verification codes)
    try:
        valid = validate_email(email)
        return valid.email  # Return the normalized email address
    except EmailNotValidError as e:
        print(str(e))
        return False

#User Table
class User(db.Model):
    id=db.Column(db.Integer, primary_key=True)
    username=db.Column(db.String(50), unique=True, nullable=False)
    password_hash=db.Column(db.String(100), nullable=False)
    email=db.Column(db.String(1000), unique=True, nullable=False)
    tokens=db.Column(db.Integer, nullable=False, default=0)
    #id, username, password_hash, email, tokens
    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)


#Symptoms Table
class Symptoms(db.Model):
    id=db.Column(db.Integer, primary_key=True)
    user_id=db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    datetime=db.Column(db.DateTime, default=datetime.datetime.now(datetime.timezone.utc), nullable=False)
    symptoms=db.Column(db.JSON, nullable=True)  # Store symptoms as a list or dict
    #id, user_id, datetime, symptoms
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'datetime': self.datetime.isoformat() if self.datetime else None,
            'symptoms': self.symptoms,
        }
    
#Prediction Results Table
class Predict1Results(db.Model):
    id=db.Column(db.Integer, primary_key=True)
    user_id=db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    datetime=db.Column(db.DateTime, default=datetime.datetime.now(datetime.timezone.utc), nullable=False)
    result=db.Column(db.String(1000), nullable=True)
    #id, user_id, datetime, result
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'datetime': self.datetime.isoformat() if self.datetime else None,
            'result': self.result,
        }

#Mental Health Notes Table
class MentalHealthNotes(db.Model):
    id=db.Column(db.Integer, primary_key=True)
    user_id=db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    datetime=db.Column(db.DateTime, default=datetime.datetime.now(datetime.timezone.utc), nullable=False)
    notes=db.Column(db.Text, nullable=True)
    #id, user_id, datetime, notes
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'datetime': self.datetime.isoformat() if self.datetime else None,
            'notes': self.notes,
        }

@app.route('/user/register', methods=['POST'])#Registration Endpoint (POST 1)
def register():#No JWT
    #uname, pwd, email
    data = flask.request.get_json()
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    if not username or not password or not email:
        return flask.jsonify({'msg': 'Missing username, password or email'}), 400
    if User.query.filter_by(username=username).first():
        return flask.jsonify({'msg': 'User already exists'}), 400
    email_status = check_email(email)
    if email_status==False:
        return flask.jsonify({'msg': 'Invalid email address'}), 400
    user = User(username=username, password_hash=password, email=email_status)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return flask.jsonify({'msg': 'User registered successfully'}), 201

@app.route('/protected/utokens', methods=['PUT'])#Token update endpoint (PUT 1)
@jwt_required() #Protected Path
def update_tokens():
    #tokens
    data=flask.request.get_json()
    tokens=data.get('tokens')
    user = User.query.get(get_jwt_identity())
    if not user:
        return flask.jsonify({'msg': 'User not found'}), 404
    user.tokens = tokens
    db.session.commit()
    return flask.jsonify({'msg': 'Tokens updated successfully'}), 200

@app.route('/user/login', methods=['POST'])#Login endpoint (POST 2)
def login():#No JWT
    #uname, pwd
    data=flask.request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return flask.jsonify({'msg': 'Missing username or password'}), 400
    user=User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return flask.jsonify({'msg': 'Invalid username or password'}), 401
    access_token = create_access_token(identity=str(user.id))
    return flask.jsonify(access_token), 200

@app.route('/user/delete', methods=['DELETE'])#Delete user Endpoint (DELETE 1)
@jwt_required() #Protected Path
def delete_user():
    current_user=get_jwt_identity()
    user=User.query.get(current_user)
    if not user:
        return flask.jsonify({'msg': 'User not found'}), 404
    Symptoms.query.filter_by(user_id=user.id).delete()
    Predict1Results.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    return flask.jsonify({'msg': 'User and associated data deleted successfully'}), 200

@app.route('/protected/symptoms/get/latest', methods=['GET'])#Get latest symptoms endpoint (GET 1)
@jwt_required() #Protected Path
def get_latest_symptoms():
    current_user = get_jwt_identity()
    user = User.query.get(current_user)
    if not user:
        return flask.jsonify({'msg': 'User not found'}), 404
    latest_symptom = Symptoms.query.filter_by(user_id=user.id).order_by(desc(Symptoms.datetime)).first()
    if not latest_symptom:
        return flask.jsonify({'msg': 'No symptoms found for this user'}), 404
    return flask.jsonify(latest_symptom.to_dict()), 200

@app.route('/protected/symptoms/add', methods=['POST'])#Add symptoms endpoint (POST 3)
@jwt_required() #Protected path
def add_symptoms():
    #symptoms [int]
    current_user = get_jwt_identity()
    user = User.query.get(current_user)
    if not user:
        return flask.jsonify({'msg': 'User not found'}), 404
    data = flask.request.get_json()
    symp_list=data.get('symptoms', [])
    if not symp_list:
        return flask.jsonify({'msg': 'No symptoms provided'}), 400
    new_symptoms = Symptoms(user_id=user.id, symptoms=symp_list)
    db.session.add(new_symptoms)
    db.session.commit()
    return flask.jsonify({'msg': 'Symptoms added successfully'}), 201

@app.route('/protected/predict1', methods=['POST'])#Predict1 endpoint (POST 4)
@jwt_required() #Protected Path
def predict1():
    current_user = get_jwt_identity()
    user = User.query.get(current_user)
    if not user:
        return flask.jsonify({'msg': 'User not found'}), 404
    latest_symptom = Symptoms.query.filter_by(user_id=user.id).order_by(desc(Symptoms.datetime)).first()
    if not latest_symptom:
        return flask.jsonify({'msg': 'No symptoms found for this user'}), 404
    predict1_url=''
    headers = {
        'Authorization': 'Bearer ',
        'Content-Type': 'application/json'
    }
    data = {
        'input': latest_symptom.symptoms,
    }
    response = requests.post(predict1_url, headers=headers, json=data)#Send request to external API
    if response.status_code != 200:
        print(response.status_code, response.text)
        return flask.jsonify({'msg': 'Error in prediction'}), 400
    prediction_result = response.json()
    prediction_result=prediction_result[0]
    new_result = Predict1Results(user_id=user.id, result=prediction_result)
    db.session.add(new_result)
    db.session.commit()
    return flask.jsonify({'msg': 'Prediction made successfully', 'result': prediction_result})

@app.route('/protected/predict1/get/latest', methods=['GET'])#Get latest prediction endpoint (GET 2)
@jwt_required() #Protected Path
def get_latest_prediction():
    current_user = get_jwt_identity()
    user = User.query.get(current_user)
    if not user:
        return flask.jsonify({'msg': 'User not found'}), 404
    latest_prediction = Predict1Results.query.filter_by(user_id=user.id).order_by(desc(Predict1Results.datetime)).first()
    if not latest_prediction:
        return flask.jsonify({'msg': 'No predictions found for this user'}), 404
    return flask.jsonify(latest_prediction.to_dict()), 200

@app.route('/protected/user/get/data/basic', methods=['GET'])#Get user info endpoint (GET 3)
@jwt_required() #Protected Path
def get_user_info():
    current_user = get_jwt_identity()
    user = User.query.get(current_user)
    if not user:
        return flask.jsonify({'msg': 'User not found'}), 404
    user_info = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'tokens': user.tokens,
    }
    return flask.jsonify(user_info), 200

@app.route('/protected/symptoms/get/all', methods=['GET'])#Get all symptoms endpoint (GET 4)
@jwt_required() #Protected Path
def get_all_symptoms():
    current_user = get_jwt_identity()
    user = User.query.get(current_user)
    if not user:
        return flask.jsonify({'msg': 'User not found'}), 404
    symptoms = Symptoms.query.filter_by(user_id=user.id).all()
    return flask.jsonify([s.to_dict() for s in symptoms]), 200

@app.route('/protected/predict1/get/all', methods=['GET'])#Get all predictions endpoint (GET 5)
@jwt_required() #Protected Path
def get_all_predictions():
    current_user=get_jwt_identity()
    user=User.query.get(current_user)
    if not user:
        return flask.jsonify({'msg': 'User not found'}), 404
    predictions = Predict1Results.query.filter_by(user_id=user.id).all()
    return flask.jsonify([p.to_dict() for p in predictions]), 200

@app.route('/time/UTC', methods=['GET'])#Get time endpoint (UTC) (GET 6)
def get_current_time():#No JWT
    current_time = datetime.datetime.now(datetime.timezone.utc)
    return flask.jsonify({'current_time': current_time.isoformat()}), 200

@app.route('/time/eastern', methods=['GET'])#Get time endpoint (Eastern) (GET 7)
def get_eastern_time():#No JWT
    eastern_time=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5)))
    return flask.jsonify({'current_time': eastern_time.isoformat()}), 200

@app.route('/test', methods=['GET'])#Test endpoint (GET 8)
def test():#No JWT
    return flask.jsonify({'msg': 'Test endpoint is working!'}), 200

@app.route('/protected/mentalHealth/add', methods=['POST'])#Add mental health notes endpoint (POST 5)
@jwt_required() #Protected Path
def add_mental_health_notes():
    #notes
    current_user=get_jwt_identity()
    user=User.query.get(current_user)
    if not user:
        return flask.jsonify({'msg': 'User not found'}), 404
    data=flask.request.get_json()
    notes=data.get('mental_health_notes')
    if not notes:
        return flask.jsonify({'msg': 'No notes provided'}), 400
    new_note = MentalHealthNotes(user_id=user.id, notes=notes)
    db.session.add(new_note)
    db.session.commit()
    return flask.jsonify({'msg': 'Mental health notes added successfully'}), 201

@app.route('/protected/mentalHealth/get/latest', methods=['GET'])#Get latest mental health notes endpoint (GET 9)
@jwt_required() #Protected Path
def get_latest_mental_health_notes():
    current_user=get_jwt_identity()
    user=User.query.get(current_user)
    if not user:
        return flask.jsonify({'msg': 'User not found'}), 404
    latest_note = MentalHealthNotes.query.filter_by(user_id=user.id).order_by(desc(MentalHealthNotes.datetime)).first()
    if not latest_note:
        return flask.jsonify({'msg': 'No mental health notes found for this user'}), 404
    return flask.jsonify(latest_note.to_dict()), 200

@app.route('/protected/mentalHealth/get/all', methods=['GET'])#Get all mental health notes endpoint (GET 10)
@jwt_required() #Protected Path
def get_all_mental_health_notes():
    current_user=get_jwt_identity()
    user=User.query.get(current_user)
    if not user:
        return flask.jsonify({'msg': 'User not found'}), 404
    notes=MentalHealthNotes.query.filter_by(user_id=user.id).all()
    return flask.jsonify([n.to_dict() for n in notes]), 200

if __name__ == '__main__':
    with app.app_context():
        print("Creating Database Tables...")
        db.create_all()#Create all database tables
        print("App Running...")
        app.run(debug=True)#Run Flask Application in debug mode
