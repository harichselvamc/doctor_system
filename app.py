from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
import re
import hashlib
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24)

# MongoDB connection
client = MongoClient("mongodb://localhost:27017")
db = client["appointment_system"]

# Collections
patients = db["patients"]
doctors = db["doctors"]
appointments = db["appointments"]
messages = db["messages"]

# Initialize admin account if not exists
if db.admin.count_documents({}) == 0:
    admin_password = hashlib.sha256("adminpassword".encode()).hexdigest()
    db.admin.insert_one({"username": "admin", "password": admin_password})

# Login decorators
def login_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'logged_in' not in session:
                flash('Please login to access this page', 'danger')
                return redirect(url_for('index'))
            if session['role'] != role:
                flash('You do not have permission to access this page', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        message = request.form['message']
        
        messages.insert_one({
            'name': name,
            'email': email,
            'phone': phone,
            'message': message,
            'date': datetime.now()
        })
        
        flash('Message sent successfully!', 'success')
        return redirect(url_for('index'))
    return render_template('index.html')

# Patient Routes
@app.route('/patient/register', methods=['GET', 'POST'])
def patient_register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        phone = request.form['phone']
        age = request.form['age']
        height = request.form['height']
        weight = request.form['weight']
        blood_group = request.form['blood_group']
        allergies = request.form['allergies']
        previous_health_issues = request.form['previous_health_issues']
        smoking = 'smoking' in request.form
        drinking = 'drinking' in request.form
        
        # Check if email already exists
        if patients.find_one({'email': email}):
            flash('Email already registered', 'danger')
            return redirect(url_for('patient_register'))
        
        # Hash password
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        # Insert patient
        patients.insert_one({
            'name': name,
            'email': email,
            'password': hashed_password,
            'phone': phone,
            'age': age,
            'height': height,
            'weight': weight,
            'blood_group': blood_group,
            'allergies': allergies,
            'previous_health_issues': previous_health_issues,
            'smoking': smoking,
            'drinking': drinking,
            'registered_on': datetime.now()
        })
        
        flash('Registration successful! Please login', 'success')
        return redirect(url_for('index'))
    
    return render_template('index.html')

@app.route('/patient/login', methods=['POST'])
def patient_login():
    email = request.form['email']
    password = request.form['password']
    
    # Hash password
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    
    # Find patient
    patient = patients.find_one({'email': email, 'password': hashed_password})
    
    if patient:
        session['logged_in'] = True
        session['role'] = 'patient'
        session['email'] = email
        session['name'] = patient['name']
        session['id'] = str(patient['_id'])
        flash('Login successful!', 'success')
        return redirect(url_for('patient_dashboard'))
    else:
        flash('Invalid login credentials', 'danger')
        return redirect(url_for('index'))

@app.route('/patient/dashboard')
@login_required('patient')
def patient_dashboard():
    # Get patient appointments
    patient_appointments = list(appointments.find({'patient_id': session['id']}).sort('date', -1))
    
    # Get all doctors for booking
    doctor_list = list(doctors.find())
    
    return render_template('patient_dashboard.html', 
                           appointments=patient_appointments, 
                           doctors=doctor_list)

@app.route('/patient/book_appointment', methods=['POST'])
@login_required('patient')
def book_appointment():
    doctor_id = request.form['doctor_id']
    appointment_date = request.form['appointment_date']
    appointment_time = request.form['appointment_time']
    
    # Get doctor details
    doctor = doctors.find_one({'_id': ObjectId(doctor_id)})
    
    # Create appointment
    appointments.insert_one({
        'patient_id': session['id'],
        'patient_name': session['name'],
        'doctor_id': doctor_id,
        'doctor_name': doctor['name'],
        'department': doctor['department'],
        'fees': doctor['consultancy_fees'],
        'date': appointment_date,
        'time': appointment_time,
        'status': 'scheduled',
        'remarks': '',
        'created_on': datetime.now(),
        'deleted': False,
        'deleted_by': ''
    })
    
    flash('Appointment booked successfully!', 'success')
    return redirect(url_for('patient_dashboard'))

@app.route('/patient/delete_appointment/<appointment_id>')
@login_required('patient')
def patient_delete_appointment(appointment_id):
    # Update appointment to deleted
    appointments.update_one(
        {'_id': ObjectId(appointment_id)},
        {'$set': {'deleted': True, 'deleted_by': session['name'], 'status': 'cancelled'}}
    )
    
    flash('Appointment cancelled successfully!', 'success')
    return redirect(url_for('patient_dashboard'))

@app.route('/patient/logout')
def patient_logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

# Doctor Routes
@app.route('/doctor/login', methods=['POST'])
def doctor_login():
    email = request.form['email']
    password = request.form['password']
    
    # Hash password
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    
    # Find doctor
    doctor = doctors.find_one({'email': email, 'password': hashed_password})
    
    if doctor:
        session['logged_in'] = True
        session['role'] = 'doctor'
        session['email'] = email
        session['name'] = doctor['name']
        session['id'] = str(doctor['_id'])
        flash('Login successful!', 'success')
        return redirect(url_for('doctor_dashboard'))
    else:
        flash('Invalid login credentials', 'danger')
        return redirect(url_for('index'))

@app.route('/doctor/dashboard')
@login_required('doctor')
def doctor_dashboard():
    # Get doctor appointments
    doctor_appointments = list(appointments.find({
        'doctor_id': session['id'],
        'deleted': False
    }).sort('date', -1))
    
    # Get attended appointments history
    appointment_history = list(appointments.find({
        'doctor_id': session['id'],
        'status': 'attended'
    }).sort('date', -1))
    
    return render_template('doctor_dashboard.html', 
                           appointments=doctor_appointments,
                           appointment_history=appointment_history)

@app.route('/doctor/update_appointment/<appointment_id>', methods=['POST'])
@login_required('doctor')
def update_appointment(appointment_id):
    status = request.form['status']
    remarks = request.form['remarks']
    
    # Update appointment
    appointments.update_one(
        {'_id': ObjectId(appointment_id)},
        {'$set': {'status': status, 'remarks': remarks}}
    )
    
    flash('Appointment updated successfully!', 'success')
    return redirect(url_for('doctor_dashboard'))

@app.route('/doctor/delete_appointment/<appointment_id>')
@login_required('doctor')
def doctor_delete_appointment(appointment_id):
    # Update appointment to deleted
    appointments.update_one(
        {'_id': ObjectId(appointment_id)},
        {'$set': {'deleted': True, 'deleted_by': session['name'], 'status': 'cancelled'}}
    )
    
    flash('Appointment cancelled successfully!', 'success')
    return redirect(url_for('doctor_dashboard'))

@app.route('/doctor/logout')
def doctor_logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

# Admin Routes
@app.route('/admin/login', methods=['POST'])
def admin_login():
    # Hardcoded admin credentials for testing
    username = 'admin'
    password = 'adminpassword'
    
    # Hash password
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    
    # Find admin
    admin = db.admin.find_one({'username': username, 'password': hashed_password})
    
    if admin:
        session['logged_in'] = True
        session['role'] = 'admin'
        session['username'] = username
        flash('Login successful!', 'success')
        return redirect(url_for('admin_dashboard'))
    else:
        flash('Invalid login credentials', 'danger')
        return redirect(url_for('index'))


@app.route('/admin/dashboard')
@login_required('admin')
def admin_dashboard():
    # Get counts for dashboard
    doctor_count = doctors.count_documents({})
    patient_count = patients.count_documents({})
    appointment_count = appointments.count_documents({})
    message_count = messages.count_documents({})
    
    # Get doctor list
    doctor_list = list(doctors.find())
    
    # Get patient list
    patient_list = list(patients.find())
    
    # Get appointment list
    appointment_list = list(appointments.find().sort('date', -1))
    
    # Get message list
    message_list = list(messages.find().sort('date', -1))
    
    return render_template('admin_dashboard.html',
                           doctor_count=doctor_count,
                           patient_count=patient_count,
                           appointment_count=appointment_count,
                           message_count=message_count,
                           doctors=doctor_list,
                           patients=patient_list,
                           appointments=appointment_list,
                           messages=message_list)

@app.route('/admin/add_doctor', methods=['POST'])
@login_required('admin')
def add_doctor():
    name = request.form['name']
    email = request.form['email']
    password = request.form['password']
    confirm_password = request.form['confirm_password']
    department = request.form['department']
    consultancy_fees = request.form['consultancy_fees']
    
    # Check if passwords match
    if password != confirm_password:
        flash('Passwords do not match', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    # Check if email already exists
    if doctors.find_one({'email': email}):
        flash('Email already registered', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    # Hash password
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    
    # Insert doctor
    doctors.insert_one({
        'name': name,
        'email': email,
        'password': hashed_password,
        'department': department,
        'consultancy_fees': consultancy_fees,
        'created_on': datetime.now()
    })
    
    flash('Doctor added successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_doctor/<doctor_id>')
@login_required('admin')
def delete_doctor(doctor_id):
    # Delete doctor
    doctors.delete_one({'_id': ObjectId(doctor_id)})
    
    # Update related appointments
    appointments.update_many(
        {'doctor_id': doctor_id},
        {'$set': {'deleted': True, 'deleted_by': 'admin', 'status': 'cancelled'}}
    )
    
    flash('Doctor deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_patient/<patient_id>')
@login_required('admin')
def delete_patient(patient_id):
    # Delete patient
    patients.delete_one({'_id': ObjectId(patient_id)})
    
    # Update related appointments
    appointments.update_many(
        {'patient_id': patient_id},
        {'$set': {'deleted': True, 'deleted_by': 'admin', 'status': 'cancelled'}}
    )
    
    flash('Patient deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_message/<message_id>')
@login_required('admin')
def delete_message(message_id):
    # Delete message
    messages.delete_one({'_id': ObjectId(message_id)})
    
    flash('Message deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)